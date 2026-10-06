#!/usr/bin/env python3
"""Collect the fixed branch-two DAgger source schedules.

This finite driver does not fit a model or write the campaign RUN.json. It
freezes one Runtime descriptor and the native binaries, collects separate
train and dev schedules, replays and summarizes both, then checks setup-ID
separation. Root must authorize the run after the active MPS job has ended.
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
sys.path.insert(0, str(ROOT / "benchmarks/strength/native"))
from runtime import Runtime, command_run  # noqa: E402
from archive_results import sha  # noqa: E402
from learner_data import (check_setup_id_disjoint, read_setup_ids,
                          validate_schedule)  # noqa: E402
from evidence import summarize as summarize_evidence  # noqa: E402
from upstream import stream  # noqa: E402

TRAIN_MASTER = 17710000000
DEV_MASTER = 17720000000
TRAIN_GAMES = 1024
DEV_GAMES = 256
WORKERS = 64
ITERATIONS = 128
DEPTH = 16
WORLD_POOL = 3
GUMBEL_MAX_CONSIDERED = 16
COMMAND_TIMEOUT_SECONDS = 21600
PARENT_CHECKPOINT = ROOT / "local/research/sprint48/refit-01/fit/model.pt"
PARENT_SHA256 = "44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f"
FROZEN_BINARIES = ROOT / "local/research/sprint48/build-controls/release/examples"
FROZEN_BUILD_REFERENCE = ROOT / "local/research/sprint48/external-02/arena/games.jsonl"
FROZEN_BUILD_SOURCES = ROOT / "local/research/sprint48/external-02/sources"
FROZEN_BINARY_SHA256 = {
    "native_policy_worker": "424d3788f936542a0080750ed8445c9d9d2960328a6b87830da4b3e032b6d3b1",
    "strength_worker": "6e90d2d1741a34d3323247833ff426b821ccaeefce683a25b34d9ff04ca306e7",
    "transfer_parity": "53c1a102617f7fbe654e31e66a9b6717f9212f5e736ca109e3282ea3269a5d07",
}
FROZEN_COMPILED_SOURCE_SHA256 = {
    "crates/splendor-agents/src/environment.rs": "69bf2f23cf87f676b728fb41bdd0988362f5b848a21a1c84323cc19112f0d45f",
    "crates/splendor-agents/src/native_environment.rs": "935f895b3b79c0828569f5a8bced6a4774e9925c4436bab067302fed2f339b44",
    "crates/splendor-agents/src/neural_search.rs": "7ddf8aa65a77283bb852ae0d98f0e1ea04fd6863f0b82885938aa78e8fe8cc91",
    "crates/splendor-arena/examples/native_policy_worker.rs": "0974ab858fa71f1b1fb6b7899872d1348f38e7fca63a649c259842b73159c2e7",
    "crates/splendor-arena/examples/native_wire/mod.rs": "04e500f2917e1667878633ad5c1874bd5e6eb64be6a5aa7ddc1d633408e78284",
}
NATIVE_PROFILE = "alphazero-native-32a27ac-v1"
SEARCH_VALIDATION = ROOT / "research/sprint48/SEARCH_VALIDATION.json"


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_records(path: Path) -> tuple[dict, list[dict]]:
    lines = path.read_text().splitlines()
    if not lines:
        raise ValueError(f"empty schedule: {path}")
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def run_logged(command: list[str], log_path: Path, cwd: Path = ROOT) -> dict:
    started = time.time()
    with log_path.open("x") as log:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            log.write(f"launch failed: {type(error).__name__}: {error}\n")
            process = None
            return_code = -1
            timed_out = False
        if process is not None:
            try:
                return_code = process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
                timed_out = False
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    return_code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    return_code = process.wait()
                timed_out = True
    item = dict(command=command, log=str(log_path), log_sha256=sha(log_path),
                pid=process.pid if process is not None else None,
                exit_code=return_code, timed_out=timed_out,
                timeout_seconds=COMMAND_TIMEOUT_SECONDS, seconds=time.time() - started)
    return item


def collect_one(split: str, master: int, games: int, output: Path,
                descriptor: Path, policy: Path, strength: Path,
                campaign_context: Path | None, run: dict) -> dict:
    target = output / split
    target.mkdir()
    schedule = ROOT / "benchmarks/strength/native/schedule.py"
    schedule_command = [sys.executable, str(schedule), "--games", str(games),
        "--master", str(master), "--workers", str(WORKERS),
        "--iterations", str(ITERATIONS), "--depth", str(DEPTH),
        "--world-pool", str(WORLD_POOL), "--search", "gumbel",
        "--gumbel-max-considered", str(GUMBEL_MAX_CONSIDERED),
        "--model", str(descriptor), "--policy-binary", str(policy),
        "--strength-binary", str(strength), "--output", str(target / "arena")]
    if campaign_context is not None:
        schedule_command.extend(("--campaign-context", str(campaign_context)))
    record = dict(split=split, source_master=master, games=games,
                  paired_setups=games // 2, profile=NATIVE_PROFILE,
                  settings=dict(iterations=ITERATIONS,
                  depth=DEPTH, world_pool=WORLD_POOL, search="gumbel",
                  gumbel_max_considered=GUMBEL_MAX_CONSIDERED,
                  chance_universes=0, root_only=False, dynamic_fpu=False),
                  commands=[])
    run["sources"].append(record)
    run["updated_utc"] = iso_now()
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")

    scheduled = run_logged(schedule_command, target / "schedule.log")
    record["commands"].append(scheduled)
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    if scheduled["exit_code"]:
        raise RuntimeError(f"schedule failed with exit {scheduled['exit_code']}; see {target / 'schedule.log'}")
    raw = target / "arena/games.jsonl"
    replay_command = [sys.executable, str(ROOT / "benchmarks/strength/native/replay.py"),
                      str(raw), "--output", str(target / "replay.json"),
                      "--strength-binary", str(strength)]
    summary_command = [sys.executable, str(ROOT / "benchmarks/strength/native/summarize.py"),
                       str(raw), "--output", str(target / "summary.json")]
    evidence_command = [sys.executable, str(ROOT / "research/sprint48/evidence.py"),
                        str(raw), "--output", str(target / "evidence.json")]
    for name, command in [("replay", replay_command), ("summary", summary_command),
                          ("evidence", evidence_command)]:
        result = run_logged(command, target / f"{name}.log")
        record["commands"].append(result)
        (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        if result["exit_code"]:
            raise RuntimeError(f"{name} failed with exit {result['exit_code']}; see {target / f'{name}.log'}")

    metadata, rows = load_records(raw)
    validate_schedule(metadata, rows, descriptor)
    expected_gumbel = dict(max_considered=GUMBEL_MAX_CONSIDERED,
                           cvisit=50, cscale=0.1, root_noise=0)
    if metadata.get("ruleset") != NATIVE_PROFILE or metadata.get("chance_universes") != 0 or \
            metadata.get("root_only") is not False or metadata.get("cpuct") != 0.4 or \
            metadata.get("fpu_reduction") != 0.02965 or metadata.get("gumbel_config") != expected_gumbel:
        raise ValueError(f"{split} schedule differs from the frozen public-profile control settings")
    evidence = summarize_evidence(metadata, rows)
    if evidence["evidence_rejections"]:
        raise ValueError(f"{split} schedule fails evidence checks: {evidence['evidence_rejections']}")
    if len(rows) != games or any(row.get("status") != "complete" for row in rows):
        raise ValueError(f"{split} schedule has incomplete games")
    ids = sorted({int(row["setup_seed"]) for row in rows})
    if len(ids) != games // 2:
        raise ValueError(f"{split} schedule has duplicate or missing setup IDs")
    low32 = [value & 0xffffffff for value in ids]
    if len(set(low32)) != len(low32):
        raise ValueError(f"{split} schedule has duplicate native low-32-bit IDs")
    (target / "setup_ids.txt").write_text("".join(f"{value}\n" for value in ids))
    (target / "setup_ids_low32.txt").write_text("".join(f"{value}\n" for value in sorted(low32)))
    record.update(status="complete", raw=str(raw), raw_sha256=sha(raw),
        replay_sha256=sha(target / "replay.json"), summary_sha256=sha(target / "summary.json"),
        evidence_sha256=sha(target / "evidence.json"), setup_ids_sha256=sha(target / "setup_ids.txt"),
        setup_ids_low32_sha256=sha(target / "setup_ids_low32.txt"),
        evidence_summary=evidence)
    run["updated_utc"] = iso_now()
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    return dict(full=ids, low32=low32)


def main() -> None:
    started = time.time()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, default=PARENT_CHECKPOINT,
                    help="Must be the frozen refit-01 parent checkpoint")
    ap.add_argument("--output", type=Path,
                    help="New collection output directory; required unless --check is used")
    ap.add_argument("--exclude-setup-ids", type=Path, required=True,
                    help="Existing corpus and prior training setup IDs")
    ap.add_argument("--binary-directory", type=Path, default=FROZEN_BINARIES)
    ap.add_argument("--port", type=int, default=19730)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--device", choices=("mps", "cpu"), default="mps")
    ap.add_argument("--campaign-context", type=Path,
                    help="Optional frozen final context; ordinary public source profiles omit it")
    ap.add_argument("--check", action="store_true",
                    help="Check locked inputs, public-profile receipt, and scheduled IDs; do not collect")
    args = ap.parse_args()
    if args.device != "mps" or args.batch != 64:
        ap.error("branch two requires the registered MPS service with batch 64")
    if args.port < 1024 or args.port > 65535:
        ap.error("port must be in 1024..65535")
    if args.check and args.output is not None:
        ap.error("--check does not accept --output")
    if not args.check and args.output is None:
        ap.error("--output is required unless --check is used")
    if args.output is not None and args.output.exists():
        ap.error(f"output already exists: {args.output}")
    checkpoint = args.checkpoint.resolve(strict=True)
    if sha(checkpoint) != PARENT_SHA256:
        ap.error("checkpoint must match the frozen refit-01 parent SHA256")
    excluded_path = args.exclude_setup_ids.resolve(strict=True)
    binary_dir = args.binary_directory.resolve(strict=True)
    policy_source = binary_dir / "native_policy_worker"
    strength_source = binary_dir / "strength_worker"
    parity_source = binary_dir / "transfer_parity"
    for path in (policy_source, strength_source, parity_source):
        if not path.is_file() or not path.stat().st_mode & 0o111:
            ap.error(f"required executable is missing or not executable: {path}")
    for path in (policy_source, strength_source, parity_source):
        expected = FROZEN_BINARY_SHA256[path.name]
        if sha(path) != expected:
            ap.error(f"{path.name} differs from the frozen build-controls binary")
    if args.campaign_context is not None:
        ap.error("the training source schedule uses the public profile, not a final-campaign context")
    if not FROZEN_BUILD_REFERENCE.is_file():
        ap.error(f"frozen build reference schedule is missing: {FROZEN_BUILD_REFERENCE}")
    reference_metadata = json.loads(FROZEN_BUILD_REFERENCE.open().readline())
    if reference_metadata.get("policy_binary_sha256") != FROZEN_BINARY_SHA256["native_policy_worker"] or \
            reference_metadata.get("strength_binary_sha256") != FROZEN_BINARY_SHA256["strength_worker"]:
        ap.error("frozen build reference does not bind the pinned executable hashes")
    for relative, expected in FROZEN_COMPILED_SOURCE_SHA256.items():
        frozen_source = FROZEN_BUILD_SOURCES / relative
        if not frozen_source.is_file() or sha(frozen_source) != expected or \
                reference_metadata.get("source_sha256", {}).get(relative) != expected:
            ap.error(f"frozen compiled-source provenance does not match: {relative}")
    if TRAIN_MASTER == DEV_MASTER:
        raise AssertionError("train and dev masters must differ")

    excluded = read_setup_ids(excluded_path)
    train_ids = [stream(TRAIN_MASTER, "setup", block) for block in range(TRAIN_GAMES // 2)]
    dev_ids = [stream(DEV_MASTER, "setup", block) for block in range(DEV_GAMES // 2)]
    check_setup_id_disjoint(train_ids, excluded)
    check_setup_id_disjoint(dev_ids, excluded | set(train_ids))
    validation = json.loads(SEARCH_VALIDATION.read_text())
    if validation.get("fixture", {}).get("profile") != NATIVE_PROFILE or \
            validation.get("new_policy_binary_sha256") != FROZEN_BINARY_SHA256["native_policy_worker"] or \
            not validation.get("default_compatibility") or \
            not all(item.get("identical_choose") for item in validation["default_compatibility"]) or \
            not any(item.get("requested", {}).get("search") == "gumbel" and
                    item.get("accepted", {}).get("search") == "gumbel" and
                    item.get("accepted", {}).get("depth") == item["requested"].get("depth") and
                    item.get("accepted", {}).get("world_pool") == item["requested"].get("world_pool") and
                    item.get("accepted", {}).get("gumbel_max_considered") ==
                    item["requested"].get("gumbel_max_considered")
                    for item in validation.get("nondefault_controls", [])):
        ap.error("frozen worker lacks the checked native public-profile control compatibility receipt")
    if args.check:
        print(json.dumps(dict(status="checked", parent_sha256=sha(checkpoint),
            public_profile=NATIVE_PROFILE, policy_binary_sha256=sha(policy_source),
            strength_binary_sha256=sha(strength_source), parity_binary_sha256=sha(parity_source),
            reference_schedule_sha256=sha(FROZEN_BUILD_REFERENCE),
            compiled_source_hashes=FROZEN_COMPILED_SOURCE_SHA256,
            exclusion_sha256=sha(excluded_path),
            train_setups=len(train_ids), dev_setups=len(dev_ids), excluded_setup_ids=len(excluded),
            train_exact_overlap=0, dev_exact_overlap=0, train_dev_exact_overlap=0,
            train_dev_low32_overlap=0, output_created=False), sort_keys=True))
        return

    output = args.output.resolve()
    output.mkdir(parents=True)
    binaries = output / "binaries"
    binaries.mkdir()
    copied = {}
    for source, name in ((policy_source, "native_policy_worker"),
                         (strength_source, "strength_worker"),
                         (parity_source, "transfer_parity")):
        target = binaries / name
        shutil.copyfile(source, target)
        target.chmod(0o755)
        copied[name] = dict(path=str(target), sha256=sha(target), source_sha256=sha(source))
    sources = [Path(__file__), ROOT / "research/training_strategy/runtime.py",
        ROOT / "research/architecture_pivots/service.py", ROOT / "research/architecture_pivots/models.py",
        ROOT / "research/architecture_pivots/export.py", ROOT / "research/e95/public_model.py",
        ROOT / "benchmarks/strength/native/schedule.py", ROOT / "benchmarks/strength/native/run.py",
        ROOT / "benchmarks/strength/native/campaign_context.py",
        ROOT / "benchmarks/strength/native/upstream.py", ROOT / "benchmarks/strength/native/replay.py",
        ROOT / "benchmarks/strength/native/summarize.py", ROOT / "research/sprint48/evidence.py"]
    source_hashes = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    for source in sources:
        target = output / "sources" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != source_hashes[str(source.relative_to(ROOT))]:
            raise ValueError(f"source copy hash mismatch: {source}")

    compiled_source_hashes = {}
    for relative, expected in FROZEN_COMPILED_SOURCE_SHA256.items():
        source = FROZEN_BUILD_SOURCES / relative
        target = output / "compiled-source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != expected:
            raise ValueError(f"frozen compiled source copy hash mismatch: {relative}")
        compiled_source_hashes[relative] = expected

    run = dict(schema="sprint48-dagger-source-collection-v1", status="running",
        started_utc=iso_now(), checkpoint=str(checkpoint), checkpoint_sha256=sha(checkpoint),
        masters=dict(train=TRAIN_MASTER, dev=DEV_MASTER),
        sizes=dict(train_games=TRAIN_GAMES, train_setups=TRAIN_GAMES // 2,
                   dev_games=DEV_GAMES, dev_setups=DEV_GAMES // 2),
        service=dict(device="mps", batch=args.batch, delay_ms=1, port=args.port),
        search=dict(iterations=ITERATIONS, depth=DEPTH, world_pool=WORLD_POOL,
                    search="gumbel", gumbel_max_considered=GUMBEL_MAX_CONSIDERED,
                    chance_universes=0, root_only=False, dynamic_fpu=False),
        binaries=copied, source_hashes=source_hashes,
        compiled_binary_provenance=dict(reference_schedule=str(FROZEN_BUILD_REFERENCE),
            reference_schedule_sha256=sha(FROZEN_BUILD_REFERENCE),
            source_schedule_source_sha256=reference_metadata.get("source_sha256"),
            compiled_source_hashes=compiled_source_hashes), sources=[],
        exclusions_path=str(excluded_path), exclusions_sha256=sha(excluded_path),
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    try:
        with Runtime([(13, checkpoint)], output / "service", args.port, "mps", batch=args.batch) as runtime:
            descriptor = runtime.descriptors[13]
            service_receipt = json.loads((output / "service/run.json").read_text())
            run["service_process"] = service_receipt
            run["descriptor"] = dict(path=str(descriptor), sha256=sha(descriptor))
            parity_result = command_run([binaries / "transfer_parity", descriptor,
                         descriptor.with_name("parity.json"), "real"], output / "parity")
            if not (descriptor.with_name("parity.json")).is_file():
                raise ValueError("runtime descriptor parity check did not write its receipt")
            run["parity"] = dict(result=parity_result,
                process=json.loads((output / "parity/process.json").read_text()),
                receipt=str(descriptor.with_name("parity.json")),
                receipt_sha256=sha(descriptor.with_name("parity.json")))
            (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
            policy = binaries / "native_policy_worker"
            strength = binaries / "strength_worker"
            train = collect_one("train", TRAIN_MASTER, TRAIN_GAMES, output,
                                descriptor, policy, strength, args.campaign_context, run)
            dev = collect_one("dev", DEV_MASTER, DEV_GAMES, output,
                              descriptor, policy, strength, args.campaign_context, run)
            check_setup_id_disjoint(train["full"], read_setup_ids(excluded_path))
            check_setup_id_disjoint(dev["full"], read_setup_ids(excluded_path) | set(train["full"]))
            if set(train["full"]) & set(dev["full"]):
                raise ValueError("train and dev setup IDs overlap")
            if set(train["low32"]) & set(dev["low32"]):
                raise ValueError("train and dev native low-32-bit setup IDs overlap")
            run["split_isolation"] = dict(train_dev_full_overlap=0,
                train_dev_low32_overlap=0, excluded_train_overlap=0, excluded_dev_overlap=0)
            run.update(status="complete", ended_utc=iso_now(), seconds=time.time() - started)
    except BaseException as error:
        run.update(status="failed", ended_utc=iso_now(), seconds=time.time() - started,
                    error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    print(json.dumps(dict(status=run["status"], output=str(output),
                          descriptor=run.get("descriptor"), split_isolation=run.get("split_isolation"))))


if __name__ == "__main__":
    main()
