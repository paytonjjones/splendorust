#!/usr/bin/env python3
"""Run one frozen, finite AlphaZero800 confirmation campaign.

This command copies inputs, starts its own inference service, checks parity,
freezes one complete protocol, and then runs the selected fixed schedule.
It has no resume or adaptive-sample-size mode. Do not use a final master for
development or tuning.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/training_strategy"))
sys.path.insert(0, str(ROOT / "research/sprint48"))
from runtime import Runtime, command_run
import freeze

MASTER = freeze.MASTER
REGISTRY = ROOT / "local/research/architecture-pivots/expanded-data.json"
AZ_SOURCE = ROOT / "local/strength/external/alphazero"
RUN_PATH = ROOT / "research/sprint48/RUN.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def copy_inputs(output: Path, checkpoint: Path, binary_directory: Path) -> tuple[dict, dict]:
    source_hashes, binary_hashes = {}, {}
    for relative, expected in freeze._sources().items():
        source = ROOT / relative
        destination = output / "sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if freeze.sha(source) != expected or freeze.sha(destination) != expected:
            raise RuntimeError(f"source changed while it was copied: {relative}")
        source_hashes[relative] = expected
    for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
        source = binary_directory / name
        destination = output / "binaries" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755)
        if freeze.sha(source) != freeze.sha(destination):
            raise RuntimeError(f"binary copy failed: {name}")
        binary_hashes[name] = freeze.sha(destination)
    copied_checkpoint = output / "input" / "candidate.pt"
    copied_checkpoint.parent.mkdir(parents=True)
    shutil.copyfile(checkpoint, copied_checkpoint)
    if freeze.sha(checkpoint) != freeze.sha(copied_checkpoint):
        raise RuntimeError("candidate checkpoint copy failed")
    return source_hashes, binary_hashes


def check_service_receipt(service_dir: Path, slot: int, config: dict,
                          checkpoint: Path, descriptor: Path) -> None:
    runtime = freeze.read_json(service_dir / "run.json")
    if runtime.get("batch") != config["batch"] or runtime.get("delay_ms") != config["delay_ms"]:
        raise RuntimeError("owned service receipt differs from frozen batch or delay")
    command = list(map(str, runtime.get("command", [])))
    expected_flags = (("--port", str(config["port"])), ("--device", config["backend"]),
        ("--batch", str(config["batch"])), ("--delay-ms", str(config["delay_ms"])))
    for flag, value in expected_flags:
        if flag not in command:
            raise RuntimeError(f"owned service command is missing {flag}")
        index = command.index(flag)
        if index + 1 >= len(command) or command[index + 1] != value:
            raise RuntimeError(f"owned service command differs at {flag}")
    if config["fast_entities"] and "--fast-entities" not in command:
        raise RuntimeError("owned service command is missing --fast-entities")
    model = runtime.get("models", {}).get(str(slot), {})
    if (model.get("source") != str(checkpoint) or model.get("checkpoint_sha256") != freeze.sha(checkpoint) or
            model.get("descriptor_sha256") != freeze.sha(descriptor)):
        raise RuntimeError("owned service did not load the frozen candidate artifacts")


def write_receipt(path: Path, receipt: dict) -> None:
    freeze._atomic_json(path, receipt)


def execute_schedule(command: list, directory: Path, deadline_unix: float,
                     receipt: dict, campaign_id: str, service_pid: int,
                     started_utc: str, run_path: Path = RUN_PATH) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    command = list(map(str, command))
    write_receipt(directory / "command.json", {"command": command, "started_at_utc": started_utc,
        "deadline_unix": deadline_unix})
    receipt.update(status="running", campaign_started_at_utc=started_utc,
        deadline_unix=deadline_unix, schedule_command=command, service_pid=service_pid)
    write_receipt(Path(receipt["output"]) / "run.json", receipt)
    freeze.update_final_campaign(run_path, campaign_id, "starting",
        {"campaign_started_at_utc": started_utc, "schedule_command": command,
         "service_pid": service_pid, "deadline_unix": deadline_unix}, seeded=False)
    log_path = directory / "output.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        receipt["schedule_pid"] = process.pid
        write_receipt(directory / "process.json", {"pid": process.pid, "command": command,
            "started_at_utc": started_utc})
        write_receipt(Path(receipt["output"]) / "run.json", receipt)
        freeze.update_final_campaign(run_path, campaign_id, "running",
            {"schedule_pid": process.pid}, seeded=True)
        remaining = deadline_unix - time.time()
        timed_out = remaining <= 0
        try:
            if timed_out:
                raise subprocess.TimeoutExpired(command, 0)
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            except ProcessLookupError:
                process.wait()
            returncode = process.returncode
    result = {"returncode": returncode, "timed_out": timed_out,
        "seconds": time.time() - dt.datetime.fromisoformat(started_utc.replace("Z", "+00:00")).timestamp()}
    write_receipt(directory / "exit.json", result)
    if timed_out:
        raise TimeoutError("final schedule reached the fixed campaign deadline; partial records are retained")
    if returncode != 0:
        raise RuntimeError(f"final schedule exited with status {returncode}; partial records are retained")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, choices=freeze.GAME_COUNTS, required=True)
    parser.add_argument("--search", choices=("puct", "gumbel"), required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--world-pool", type=int, required=True)
    parser.add_argument("--chance-universes", type=int, default=0)
    parser.add_argument("--dynamic-fpu", action="store_true")
    parser.add_argument("--gumbel-max-considered", type=int, default=16)
    parser.add_argument("--root-only", action="store_true")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--binary-directory", type=Path, default=ROOT / "target/release/examples")
    parser.add_argument("--port", type=int, default=19720)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--backend", choices=("cpu", "mps"), default="mps")
    parser.add_argument("--corpus-registry", type=Path, action="append", default=None)
    args = parser.parse_args()
    if args.games // 2 < args.workers or args.workers < 1:
        parser.error("workers must be positive and no greater than paired setup blocks")
    if args.batch < 1:
        parser.error("batch must be positive")
    if not 0 <= args.chance_universes <= 64:
        parser.error("chance-universes must be in 0..=64")
    binary_directory = args.binary_directory.resolve(strict=True)
    checkpoint = args.checkpoint.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        parser.error("output directory already exists")
    run = freeze.read_json(RUN_PATH)
    if run.get("status") != "active" or time.time() >= run.get("deadline_unix", 0):
        parser.error("campaign is inactive or its fixed deadline has passed")
    if run.get("final_campaign") is not None:
        parser.error("this RUN.json already has a final campaign record")
    if any(trial.get("status") == "running" for trial in run.get("consumed_trials", [])):
        parser.error("an exploratory external trial is still running")
    if any(branch.get("status") == "running" for branch in run.get("training_branches", [])):
        parser.error("a training branch is still running")
    registry_paths = args.corpus_registry or [REGISTRY]
    started = time.time()
    output.mkdir(parents=True, exist_ok=False)
    campaign_id = None
    final_status = None
    receipt = {"schema": "sprint48-final-run-v1", "status": "preparing",
        "started_unix": started, "output": str(output), "master": MASTER,
        "games": args.games, "search": args.search, "iterations": args.iterations,
        "depth": args.depth, "world_pool": args.world_pool,
        "chance_universes": args.chance_universes,
        "dynamic_fpu": args.dynamic_fpu,
        "gumbel_max_considered": args.gumbel_max_considered if args.search == "gumbel" else None,
        "root_only": args.root_only, "workers": args.workers, "backend": args.backend,
        "port": args.port, "batch": args.batch, "checkpoint_source": str(checkpoint),
        "checkpoint_source_sha256": freeze.sha(checkpoint)}
    write_receipt(output / "run.json", receipt)
    try:
        source_hashes, binary_hashes = copy_inputs(output, checkpoint, binary_directory)
        local_checkpoint = output / "input/candidate.pt"
        binaries = output / "binaries"
        with Runtime([(13, local_checkpoint)], output / "service", args.port, args.backend,
                     batch=args.batch, delay_ms=1) as runtime:
            descriptor = runtime.descriptors[13].resolve(strict=True)
            export_receipt = descriptor.with_name("export.json").resolve(strict=True)
            service_config = {"backend": args.backend, "batch": args.batch, "delay_ms": 1,
                "port": args.port, "fast_entities": True}
            check_service_receipt(output / "service", 13, service_config, local_checkpoint, descriptor)
            parity_directory = output / "parity-command"
            command_run([binaries / "transfer_parity", descriptor,
                descriptor.with_name("parity.json"), "real"], parity_directory)
            parity = json.loads((parity_directory / "output.log").read_text().splitlines()[0])
            if (parity.get("all_inputs_max_logit_error", float("inf")) > parity.get("output_tolerance", 0)
                    or parity.get("masked_policy_and_value_max_error", float("inf")) > parity.get("output_tolerance", 0)
                    or parity.get("real_initial_board_max_logit_error", float("inf")) > parity.get("real_logit_tolerance", 0)):
                raise RuntimeError("native descriptor parity check failed")
            proposal = {"schema": "sprint48-final-proposal-v1",
                "candidate": {"checkpoint": str(local_checkpoint), "descriptor": str(descriptor),
                    "export_receipt": str(export_receipt),
                    "policy_binary": str(binaries / "native_policy_worker"),
                    "strength_binary": str(binaries / "strength_worker"),
                    "parity_binary": str(binaries / "transfer_parity")},
                "search": {"algorithm": args.search, "iterations": args.iterations,
                    "depth": args.depth, "world_pool": args.world_pool,
                    "chance_universes": args.chance_universes,
                    "dynamic_fpu": args.dynamic_fpu,
                    "gumbel_max_considered": args.gumbel_max_considered if args.search == "gumbel" else None,
                    "root_only": args.root_only},
                "service": service_config, "games": args.games}
            campaign_id = freeze.reserve_final_campaign(RUN_PATH, output,
                {"driver_pid": os.getpid(), "service_pid": runtime.service.pid,
                 "games": args.games, "master": MASTER, "search": args.search,
                 "iterations": args.iterations, "depth": args.depth, "world_pool": args.world_pool,
                 "chance_universes": args.chance_universes,
                 "dynamic_fpu": args.dynamic_fpu,
                 "gumbel_max_considered": args.gumbel_max_considered if args.search == "gumbel" else None,
                 "root_only": args.root_only, "workers": args.workers,
                 "backend": args.backend, "batch": args.batch, "port": args.port,
                 "checkpoint_sha256": freeze.sha(local_checkpoint)})
            final_status = "freezing"
            receipt["campaign_id"] = campaign_id
            manifest = freeze.build_freeze(proposal, registry_paths,
                RUN_PATH, output, AZ_SOURCE)
            if source_hashes != manifest["source_sha256"]:
                raise RuntimeError("source snapshot differs from the final freeze fingerprint")
            manifest["freeze_sha256"] = freeze.freeze_sha(manifest)
            freeze.validate_freeze(manifest)
            freeze_path = output / "final-freeze.json"
            freeze.write_once(freeze_path, manifest, RUN_PATH)
            freeze.update_final_campaign(RUN_PATH, campaign_id, "frozen",
                {"freeze_path": str(freeze_path.resolve()), "freeze_sha256": manifest["freeze_sha256"],
                 "frozen_at_utc": manifest["frozen_at_utc"], "descriptor_sha256": freeze.sha(descriptor),
                 "export_receipt_sha256": freeze.sha(export_receipt)})
            final_status = "frozen"
            receipt.update(status="frozen", freeze_path=str(freeze_path),
                freeze_sha256=manifest["freeze_sha256"],
                source_sha256=source_hashes, binary_sha256=binary_hashes,
                descriptor=str(descriptor), descriptor_sha256=freeze.sha(descriptor),
                checkpoint_path=str(local_checkpoint), checkpoint_sha256=freeze.sha(local_checkpoint),
                export_receipt_path=str(export_receipt), export_receipt_sha256=freeze.sha(export_receipt),
                parity_exit=json.loads((parity_directory / "exit.json").read_text()))
            write_receipt(output / "run.json", receipt)
            started_utc = utc_now()
            context = {"schema": "sprint48-final-campaign-context-v1",
                "freeze_path": str(freeze_path.resolve()), "freeze_sha256": manifest["freeze_sha256"],
                "campaign_started_at_utc": started_utc, "checkpoint_path": str(local_checkpoint.resolve()),
                "checkpoint_sha256": freeze.sha(local_checkpoint), "export_receipt_path": str(export_receipt),
                "export_receipt_sha256": freeze.sha(export_receipt),
                "parity_binary_path": str((binaries / "transfer_parity").resolve()),
                "parity_binary_sha256": binary_hashes["transfer_parity"],
                "service_config": service_config | {"source_sha256": manifest["service"]["source"]["sha256"]},
                "source_sha256": source_hashes}
            context_path = output / "campaign-context.json"
            with context_path.open("x") as stream:
                stream.write(json.dumps(context, sort_keys=True, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            context_path.chmod(0o444)
            receipt.update(campaign_started_at_utc=started_utc, campaign_context_path=str(context_path))
            schedule_command = [sys.executable, ROOT / "benchmarks/strength/native/schedule.py",
                "--games", args.games, "--master", MASTER, "--workers", args.workers,
                "--iterations", args.iterations, "--search", args.search, "--model", descriptor,
                "--depth", args.depth, "--world-pool", args.world_pool,
                "--chance-universes", args.chance_universes,
                "--gumbel-max-considered", args.gumbel_max_considered,
                "--policy-binary", binaries / "native_policy_worker",
                "--strength-binary", binaries / "strength_worker",
                "--campaign-context", context_path, "--output", output / "arena"]
            if args.root_only:
                schedule_command.append("--root-only")
            if args.dynamic_fpu:
                schedule_command.append("--dynamic-fpu")
            if time.time() >= run["deadline_unix"]:
                raise TimeoutError("fixed campaign deadline passed before schedule launch")
            final_status = "starting"
            execute_schedule(schedule_command, output / "arena-command", run["deadline_unix"],
                receipt, campaign_id, runtime.service.pid, started_utc)
            final_status = "running"
            raw = output / "arena/games.jsonl"
            command_run([sys.executable, ROOT / "benchmarks/strength/native/replay.py",
                raw, "--output", output / "replay.json", "--strength-binary", binaries / "strength_worker"],
                output / "replay-command")
            command_run([sys.executable, ROOT / "benchmarks/strength/native/summarize.py",
                raw, "--output", output / "summary.json"], output / "summary-command")
            command_run([sys.executable, ROOT / "research/sprint48/evidence.py",
                raw, "--output", output / "evidence.json"], output / "evidence-command")
            metadata = json.loads(raw.read_text().splitlines()[0])
            replay = freeze.read_json(output / "replay.json")
            evidence = freeze.read_json(output / "evidence.json")
            if replay.get("checked_games") != args.games or replay.get("raw_sha256") != freeze.sha(raw):
                raise RuntimeError("replay did not verify the complete final raw file")
            claim_supported = freeze.validate_outcomes(manifest, metadata, evidence,
                context["campaign_started_at_utc"], args.games)
            for name, expected in binary_hashes.items():
                if freeze.sha(binaries / name) != expected:
                    raise RuntimeError(f"frozen binary changed during the run: {name}")
            summary = freeze.read_json(output / "summary.json")
            if summary.get("games") != args.games:
                raise RuntimeError("summary does not cover the complete final schedule")
            receipt.update(status="complete", completed_at_unix=time.time(),
                claim_supported=claim_supported, raw_sha256=freeze.sha(raw),
                replay_sha256=freeze.sha(output / "replay.json"),
                summary_sha256=freeze.sha(output / "summary.json"),
                evidence_sha256=freeze.sha(output / "evidence.json"),
                games_verified=replay["checked_games"], wall_seconds=time.time() - started,
                evidence=summary)
            final_status = "complete"
            print(json.dumps({"games": summary["games"], "statuses": summary["statuses"],
                "hoeffding95": summary["conservative_hoeffding95_missing_envelope"],
                "claim_supported": claim_supported}), flush=True)
    except BaseException as error:
        receipt.update(status="failed", failed_at_unix=time.time(), error=repr(error))
        if campaign_id is not None:
            final_status = "failed"
        raise
    finally:
        receipt["wall_seconds"] = time.time() - started
        write_receipt(output / "run.json", receipt)
        if campaign_id is not None and final_status is not None:
            fields = {"finished_at_utc": utc_now(), "driver_pid": os.getpid(),
                }
            for key in ("schedule_pid", "service_pid"):
                if receipt.get(key) is not None:
                    fields[key] = receipt[key]
            if receipt.get("error"):
                fields["error"] = receipt["error"]
            freeze.update_final_campaign(RUN_PATH, campaign_id, final_status, fields,
                seeded=receipt.get("schedule_pid") is not None)


if __name__ == "__main__":
    main()
