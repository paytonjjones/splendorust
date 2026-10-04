#!/usr/bin/env python3
"""Prepare and run the fixed 6400-vs-6400 follow-up campaign.

The default mode validates inputs and writes nothing. Pass ``--execute`` to
start the owned MPS service and the one registered schedule. This diagnostic
does not change the confirmed AlphaZero800 result or RUN.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
SPRINT = ROOT / "research/sprint48"
FOLLOWUP_PATH = SPRINT / "FOLLOWUP.json"
FREEZE_PATH = ROOT / "local/research/sprint48/final-native-retry/final-freeze.json"
DECISION_PATH = SPRINT / "FINAL_DECISION.json"
CHECKPOINT = ROOT / "local/research/sprint48/ready/first/onehot/runtime.pt"
BUILD = ROOT / "local/research/sprint48/build-dynamic/release/examples"
OUTPUT = ROOT / "local/research/sprint48/opponent-search-6400"
SCHEDULE = Path(__file__).with_name("schedule.py").resolve()
RUNNER = Path(__file__).with_name("run.py").resolve()
RUNTIME_SOURCE = ROOT / "research/training_strategy/runtime.py"
SERVICE_SOURCE = ROOT / "research/architecture_pivots/service.py"
EXPORT_SOURCE = ROOT / "research/architecture_pivots/export.py"
EVIDENCE_SOURCE = SPRINT / "evidence.py"
BUILD_VALIDATION = SPRINT / "DYNAMIC_FPU_VALIDATION.json"
REPLAY = ROOT / "benchmarks/strength/native/replay.py"
SUMMARIZE = ROOT / "benchmarks/strength/native/summarize.py"
PREFLIGHT = ROOT / "local/research/sprint48/opponent-search-preflight/setup-audit.json"
EXCLUSIONS = ROOT / "local/research/sprint48/opponent-search-preflight/excluded-setup-ids.txt"

PROFILE = "alphazero-native-search-budget-diagnostic-v1"
MASTER = 17_792_000_000
GAMES = 1000
WORKERS = 64
AZ_SIMULATIONS = 6400
PORT = 19760
BATCH = 32
DELAY_MS = 1
CANONICAL_PIDS = {"driver_pid": 38974, "service_pid": 38978, "compare_pid": 38980}
CHECKPOINT_SHA256 = "ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb"
AZ_CHECKPOINT_SHA256 = "6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07"
AZ_REVISION = "32a27ac1f85d5de2766cc5f60c2bf04e557f7836"
EXCLUSIONS_SHA256 = "6f5e7a9f13efde03bd589692f89a04af134ef5944a5e213f90f2bc51044a8a13"
SETUP_AUDIT_SHA256 = "a92ca6b397c9cffd6d0a24f9a7984377254fc5d0e0055076beffdbbdbbf91b0a"
DEADLINE_BUDGET_SECONDS = 50_400
POSTPROCESS_RESERVE_SECONDS = 900


class CampaignInterrupted(RuntimeError):
    pass


def stop_handler(signum, _frame):
    raise CampaignInterrupted(f"campaign received signal {signum}; child process cleanup requested")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_value(value) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def require_canonical_stopped(followup: dict, is_alive=pid_is_alive) -> dict:
    canonical = followup.get("canonical_diagnostic")
    if not isinstance(canonical, dict) or canonical.get("output") != "local/research/sprint48/final-canonical-diagnostic-17791000000":
        raise ValueError("FOLLOWUP canonical diagnostic record differs from the registered job")
    pids = {name: canonical.get(name) for name in CANONICAL_PIDS}
    if pids != CANONICAL_PIDS:
        raise ValueError("FOLLOWUP canonical job PIDs differ from the registered job")
    alive = [f"{name}={pid}" for name, pid in pids.items() if is_alive(pid)]
    if alive:
        raise RuntimeError("canonical MPS job is still active: " + ", ".join(alive))
    return {"pids": pids, "verified_stopped_at_utc": utc_now(),
            "recorded_status": canonical.get("status"), "output": canonical["output"]}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def expected_candidate_search() -> dict:
    return {"algorithm": "puct", "iterations": 6400, "depth": 64,
            "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True}


def source_hash_map(bundle: dict) -> dict[str, str]:
    result = {}
    for key, info in bundle["sources"].items():
        relative = key.split(":", 1)[1]
        if relative in result and result[relative] != info["sha256"]:
            raise ValueError(f"frozen and campaign source hashes differ for {relative}")
        result[relative] = info["sha256"]
    return result


def build_reservation(schedule_output: Path, descriptor_sha256: str, descriptor_path: Path,
                      bundle: dict) -> dict:
    source_sha256 = source_hash_map(bundle)
    candidate_artifacts = {
        "binaries": {name: {"path": info["path"], "sha256": info["sha256"]}
                     for name, info in bundle["binaries"].items()},
        "service": {
            "backend": "mps", "batch": BATCH, "delay_ms": DELAY_MS,
            "port": PORT, "fast_entities": True, "slot": 13,
            "checkpoint_path": bundle["checkpoint"]["path"],
            "checkpoint_sha256": bundle["checkpoint"]["sha256"],
            "model_pt_path": bundle["exported_artifacts"]["model_pt"]["path"],
            "model_pt_sha256": bundle["exported_artifacts"]["model_pt"]["sha256"],
            "descriptor_path": str(descriptor_path),
            "descriptor_sha256": descriptor_sha256,
            "export_receipt_path": bundle["exported_artifacts"]["export_receipt"]["path"],
            "export_receipt_sha256": bundle["exported_artifacts"]["export_receipt"]["sha256"],
            "service_receipt_path": bundle["service_receipt"]["path"],
            "service_receipt_sha256": bundle["service_receipt"]["sha256"],
            "parity_input_path": bundle["exported_artifacts"]["parity_input"]["path"],
            "parity_input_sha256": bundle["exported_artifacts"]["parity_input"]["sha256"],
            "parity_receipt_path": bundle["exported_artifacts"]["parity_receipt"]["path"],
            "parity_receipt_sha256": bundle["exported_artifacts"]["parity_receipt"]["sha256"],
        },
    }
    reservation = {
        "profile": PROFILE,
        "schedule_output": str(schedule_output.resolve()),
        "master": MASTER,
        "games": GAMES,
        "opponent_simulations": AZ_SIMULATIONS,
        "candidate_search": expected_candidate_search(),
        "candidate_checkpoint_path": bundle["checkpoint"]["path"],
        "candidate_checkpoint_sha256": CHECKPOINT_SHA256,
        "candidate_descriptor_path": str(descriptor_path),
        "candidate_descriptor_sha256": descriptor_sha256,
        "candidate_artifacts": candidate_artifacts,
        "service": candidate_artifacts["service"],
        "bundle_manifest_path": bundle["manifest_path"],
        "bundle_manifest_sha256": bundle["manifest_sha256"],
        "source_sha256": source_sha256,
    }
    return reservation


def verify_bundle(reservation: dict) -> None:
    manifest_path = Path(reservation["bundle_manifest_path"])
    if sha(manifest_path) != reservation["bundle_manifest_sha256"]:
        raise ValueError("pre-schedule bundle manifest hash differs")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("source_sha256") != reservation["source_sha256"]:
        raise ValueError("bundle manifest source hashes differ from the reservation")
    copied_sources = manifest.get("files", {}).get("sources", {})
    observed_sources = {}
    for key, item in copied_sources.items():
        path = Path(item["path"])
        if sha(path) != item["sha256"]:
            raise ValueError(f"copied source hash differs before schedule launch: {path}")
        relative = key.split(":", 1)[1]
        if relative in observed_sources and observed_sources[relative] != item["sha256"]:
            raise ValueError(f"source copies differ before schedule launch: {relative}")
        observed_sources[relative] = item["sha256"]
    if observed_sources != reservation["source_sha256"]:
        raise ValueError("copied sources do not cover the complete reservation source map")

    artifacts = reservation["candidate_artifacts"]
    for name, artifact in artifacts["binaries"].items():
        if sha(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError(f"copied candidate binary changed: {name}")
    service = artifacts["service"]
    expected_service = {"backend": "mps", "batch": BATCH, "delay_ms": DELAY_MS,
        "port": PORT, "fast_entities": True, "slot": 13}
    if any(service.get(key) != value for key, value in expected_service.items()):
        raise ValueError("service configuration differs from the registered resource plan")
    for path_key, digest_key in (("checkpoint_path", "checkpoint_sha256"),
            ("model_pt_path", "model_pt_sha256"), ("descriptor_path", "descriptor_sha256"),
            ("export_receipt_path", "export_receipt_sha256"),
            ("service_receipt_path", "service_receipt_sha256"),
            ("parity_input_path", "parity_input_sha256"),
            ("parity_receipt_path", "parity_receipt_sha256")):
        if sha(Path(service[path_key])) != service[digest_key]:
            raise ValueError(f"service candidate artifact changed: {path_key}")
    if (service["checkpoint_sha256"] != reservation["candidate_checkpoint_sha256"] or
            service["descriptor_sha256"] != reservation["candidate_descriptor_sha256"] or
            service["checkpoint_path"] != reservation["candidate_checkpoint_path"] or
            service["descriptor_path"] != reservation["candidate_descriptor_path"]):
        raise ValueError("top-level candidate paths and service artifact binding differ")


def validate_followup_plan(followup: dict) -> dict:
    if followup.get("schema") != "sprint48-followup-plan-v1" or followup.get("status") != "active":
        raise ValueError("FOLLOWUP plan is not active")
    deadline = dt.datetime.fromisoformat(followup["deadline_utc"].replace("Z", "+00:00"))
    deadline_unix = deadline.timestamp()
    if time.time() >= deadline_unix:
        raise TimeoutError("original Sprint 48 deadline has passed")
    plan = followup.get("opponent_search", {})
    expected = {
        "candidate_checkpoint_sha256": CHECKPOINT_SHA256,
        "candidate_search": expected_candidate_search(),
        "opponent_revision": AZ_REVISION,
        "opponent_checkpoint_sha256": AZ_CHECKPOINT_SHA256,
        "opponent_simulations": AZ_SIMULATIONS,
        "games": GAMES,
        "paired_blocks": 500,
        "master": MASTER,
        "adaptive_stopping": False,
        "implementation_budget_seconds": 7200,
        "job_budget_seconds": DEADLINE_BUDGET_SECONDS,
        "exclusions_sha256": EXCLUSIONS_SHA256,
        "seed_audit": "local/research/sprint48/opponent-search-preflight/setup-audit.json",
    }
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValueError(f"FOLLOWUP opponent_search differs from the registered plan at {key}")
    if plan.get("reservation") is not None:
        raise ValueError("the registered one-shot master already has a reservation")
    if plan.get("status") not in {"preparing_harness", "ready"}:
        raise ValueError("FOLLOWUP opponent search is not ready to reserve its fixed master")
    return {"deadline_unix": deadline_unix, "plan": plan}


def validate_pinned_upstream(decision: dict) -> dict:
    source = ROOT / "local/strength/external/alphazero"
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain",
                                     "--untracked-files=no"], text=True).strip()
    checkpoint = source / "splendor/pretrained_2players.pt"
    if revision != AZ_REVISION or dirty or sha(checkpoint) != AZ_CHECKPOINT_SHA256:
        raise ValueError("pinned AlphaZero checkout or checkpoint changed")
    return {"source": str(source), "revision": revision, "working_tree_clean": not bool(dirty),
            "checkpoint_path": str(checkpoint), "checkpoint_sha256": sha(checkpoint),
            "external_config_800": decision["target"]["external_config"]}


def preflight(output: Path = OUTPUT, is_alive=pid_is_alive) -> dict:
    output = Path(output).resolve()
    if output != OUTPUT.resolve():
        raise ValueError("campaign output must use the registered new path")
    if output.exists():
        raise ValueError("campaign output already exists; never reuse a failed or partial attempt")
    followup = json.loads(FOLLOWUP_PATH.read_text())
    plan = validate_followup_plan(followup)
    stopped = require_canonical_stopped(followup, is_alive)
    freeze_manifest = json.loads(FREEZE_PATH.read_text())
    decision = json.loads(DECISION_PATH.read_text())
    validate_build_inputs(followup, freeze_manifest, decision)
    checkpoint = CHECKPOINT.resolve(strict=True)
    if sha(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError("candidate checkpoint changed")
    if sha(PREFLIGHT) != SETUP_AUDIT_SHA256 or sha(EXCLUSIONS) != EXCLUSIONS_SHA256:
        raise ValueError("setup seed preflight changed")
    validation = json.loads(BUILD_VALIDATION.read_text())
    if any(item.get("status") != "passed" for item in validation.get("checks", [])):
        raise ValueError("dynamic-FPU binary validation did not pass every check")
    binary_hashes = {}
    for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
        relative = f"local/research/sprint48/build-dynamic/release/examples/{name}"
        actual = sha(BUILD / name)
        if actual != validation.get("binary_sha256", {}).get(relative):
            raise ValueError(f"dynamic-FPU binary differs from its passed validation receipt: {name}")
        binary_hashes[name] = actual
    upstream = validate_pinned_upstream(decision)
    sys.path.insert(0, str(Path(__file__).parent))
    import schedule as diagnostic_schedule
    setup_seeds = diagnostic_schedule.fresh_master(MASTER, GAMES, output / "schedule")
    return {"output": str(output), "deadline_unix": plan["deadline_unix"],
            "canonical_job_stopped": stopped, "candidate_checkpoint_sha256": sha(checkpoint),
            "binary_sha256": binary_hashes, "upstream": upstream,
            "setup_seed_count": len(setup_seeds), "profile": PROFILE,
            "games": GAMES, "master": MASTER, "opponent_simulations": AZ_SIMULATIONS,
            "candidate_search": expected_candidate_search()}


def reservation_document(reservation: dict) -> dict:
    return {"reservation": reservation, "reservation_sha256": hash_value(reservation),
            "seed_consumed": False, "status": "reserved"}


def lock_followup(path: Path):
    lock = Path(path).with_name(Path(path).name + ".lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    return lock


def reserve_followup(path: Path, reservation: dict) -> str:
    lock = lock_followup(path)
    try:
        document = json.loads(Path(path).read_text())
        validate_followup_plan(document)
        opponent = document["opponent_search"]
        reservation_info = reservation_document(reservation)
        opponent["reservation"] = reservation_info["reservation"]
        opponent["reservation_sha256"] = reservation_info["reservation_sha256"]
        opponent["seed_consumed"] = False
        opponent["status"] = "reserved"
        atomic_json(path, document)
        return reservation_info["reservation_sha256"]
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def update_reservation(path: Path, reservation_sha256: str, *, seed_consumed: bool,
                       status: str, fields: dict | None = None) -> None:
    lock = lock_followup(path)
    try:
        document = json.loads(Path(path).read_text())
        opponent = document.get("opponent_search", {})
        if opponent.get("reservation_sha256") != reservation_sha256:
            raise ValueError("FOLLOWUP one-shot reservation changed")
        opponent["seed_consumed"] = bool(seed_consumed or opponent.get("seed_consumed"))
        if fields:
            opponent.update(fields)
        opponent["status"] = status
        atomic_json(path, document)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def validate_build_inputs(followup: dict, freeze: dict, decision: dict) -> None:
    if freeze.get("freeze_sha256") != decision.get("freeze_sha256"):
        raise ValueError("frozen proof does not match FINAL_DECISION")
    if decision.get("status") != "confirmed_decisive_native_win":
        raise ValueError("the prior AlphaZero800 proof is not confirmed")
    if decision.get("candidate", {}).get("checkpoint_sha256") != CHECKPOINT_SHA256:
        raise ValueError("confirmed proof candidate checkpoint differs")
    if (decision.get("target", {}).get("revision") != AZ_REVISION or
            decision.get("target", {}).get("checkpoint", {}).get("sha256") != AZ_CHECKPOINT_SHA256):
        raise ValueError("pinned AlphaZero target differs from the registered target")
    plan = followup["opponent_search"]
    if plan["candidate_checkpoint_sha256"] != freeze["candidate"]["checkpoint"]["sha256"]:
        raise ValueError("FOLLOWUP checkpoint differs from the proof freeze")


def _copy_hash(source: Path, target: Path, expected: str | None = None) -> str:
    source = Path(source).resolve(strict=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    actual = sha(target)
    if expected is not None and actual != expected:
        raise ValueError(f"copied artifact hash differs: {source}")
    if sha(source) != actual:
        raise ValueError(f"artifact changed while it was copied: {source}")
    return actual


def copy_provenance(output: Path, freeze: dict, decision: dict, checkpoint: Path,
                    binary_directory: Path) -> dict:
    files: dict[str, dict] = {}
    source_root = output / "provenance/sources"
    for relative, expected in sorted(freeze["source_sha256"].items()):
        source = ROOT / relative
        target = source_root / relative
        digest = _copy_hash(source, target, expected)
        files[f"frozen-source:{relative}"] = {"path": str(target), "sha256": digest}
    extras = {
        "research/sprint48/opponent_search/run_campaign.py": Path(__file__).resolve(),
        "research/sprint48/opponent_search/run.py": RUNNER,
        "research/sprint48/opponent_search/schedule.py": SCHEDULE,
        "research/training_strategy/runtime.py": RUNTIME_SOURCE,
        "research/architecture_pivots/service.py": SERVICE_SOURCE,
        "research/architecture_pivots/export.py": EXPORT_SOURCE,
        "research/sprint48/evidence.py": EVIDENCE_SOURCE,
        "benchmarks/strength/native/replay.py": REPLAY,
        "benchmarks/strength/native/summarize.py": SUMMARIZE,
        "research/sprint48/DYNAMIC_FPU_VALIDATION.json": BUILD_VALIDATION,
        "local/research/sprint48/opponent-search-preflight/setup-audit.json": PREFLIGHT,
        "local/research/sprint48/opponent-search-preflight/excluded-setup-ids.txt": EXCLUSIONS,
    }
    for relative, source in extras.items():
        target = output / "provenance/campaign-sources" / relative
        digest = _copy_hash(source, target)
        files[f"campaign-source:{relative}"] = {"path": str(target), "sha256": digest}
    binaries = {}
    for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
        source = binary_directory / name
        target = output / "binaries" / name
        digest = _copy_hash(source, target)
        target.chmod(0o755)
        binaries[name] = {"source": str(source), "path": str(target), "sha256": digest}
    target_checkpoint = output / "input/candidate.pt"
    checkpoint_sha = _copy_hash(checkpoint, target_checkpoint, CHECKPOINT_SHA256)
    checkpoint_info = {"source": str(checkpoint), "path": str(target_checkpoint), "sha256": checkpoint_sha}
    copied_freeze = output / "provenance/final-freeze.json"
    freeze_file_sha256 = _copy_hash(FREEZE_PATH, copied_freeze, sha(FREEZE_PATH))
    copied_decision = output / "provenance/FINAL_DECISION.json"
    _copy_hash(DECISION_PATH, copied_decision)
    return {"sources": files, "binaries": binaries, "checkpoint": checkpoint_info,
            "freeze_path": str(copied_freeze), "freeze_sha256": freeze["freeze_sha256"],
            "freeze_file_sha256": freeze_file_sha256,
            "decision_path": str(copied_decision), "decision_sha256": sha(copied_decision)}


def write_bundle_manifest(output: Path, freeze: dict, bundle: dict) -> dict:
    bundle["source_sha256"] = source_hash_map(bundle)
    manifest_path = output / "provenance/bundle-manifest.json"
    atomic_json(manifest_path, {"schema": "sprint48-opponent-search-bundle-v1",
        "profile": PROFILE, "freeze_sha256": freeze["freeze_sha256"],
        "master": MASTER, "games": GAMES, "candidate_search": expected_candidate_search(),
        "candidate_checkpoint_sha256": CHECKPOINT_SHA256,
        "descriptor_sha256": bundle["descriptor_sha256"],
        "source_sha256": bundle["source_sha256"], "files": bundle})
    bundle["manifest_path"] = str(manifest_path)
    bundle["manifest_sha256"] = sha(manifest_path)
    return bundle


def service_check(output: Path, checkpoint: Path, descriptor: Path) -> dict:
    runtime = json.loads((output / "service/run.json").read_text())
    command = list(map(str, runtime.get("command", [])))
    required = {"--port": str(PORT), "--device": "mps", "--batch": str(BATCH), "--delay-ms": str(DELAY_MS)}
    for flag, value in required.items():
        if flag not in command or command[command.index(flag) + 1] != value:
            raise ValueError(f"Runtime service receipt differs at {flag}")
    if "--fast-entities" not in command:
        raise ValueError("Runtime did not start the fast Entity service")
    model = runtime.get("models", {}).get("13", {})
    if (model.get("source") != str(checkpoint) or model.get("checkpoint_sha256") != CHECKPOINT_SHA256 or
            model.get("descriptor_sha256") != sha(descriptor)):
        raise ValueError("service loaded a different model or descriptor")
    return runtime


def validate_parity(output: Path, descriptor: Path) -> dict:
    output_log = output / "parity-command/output.log"
    lines = output_log.read_text().splitlines()
    if not lines:
        raise RuntimeError("native parity command returned no receipt")
    parity = json.loads(lines[0])
    tolerance = parity.get("output_tolerance", 0)
    if (parity.get("all_inputs_max_logit_error", float("inf")) > tolerance or
            parity.get("masked_policy_and_value_max_error", float("inf")) > tolerance or
            parity.get("real_initial_board_max_logit_error", float("inf")) > parity.get("real_logit_tolerance", 0)):
        raise RuntimeError("copied native transfer parity did not pass")
    result = json.loads((output / "parity-command/exit.json").read_text())
    if result.get("returncode") != 0:
        raise RuntimeError("transfer parity process failed")
    receipt_path = output / "parity-command/result.json"
    atomic_json(receipt_path, parity | {"exit": result})
    return {"path": str(receipt_path), "sha256": sha(receipt_path),
            "output_log_path": str(output_log), "output_log_sha256": sha(output_log),
            "input_path": str(descriptor.with_name("parity.json")),
            "input_sha256": sha(descriptor.with_name("parity.json")), "exit": result}


def schedule_command(schedule_output: Path, descriptor: Path, binaries: dict,
                     reservation: dict, reservation_sha256: str, owner_receipt: Path) -> list[str]:
    return [sys.executable, str(SCHEDULE), "--games", str(GAMES), "--master", str(MASTER),
            "--alphazero-simulations", str(AZ_SIMULATIONS), "--workers", str(WORKERS),
            "--iterations", "6400", "--search", "puct", "--depth", "64",
            "--world-pool", "3", "--chance-universes", "3", "--dynamic-fpu",
            "--model", str(descriptor), "--policy-binary", str(binaries["native_policy_worker"]["path"]),
            "--strength-binary", str(binaries["strength_worker"]["path"]),
            "--output", str(schedule_output), "--owner-receipt", str(owner_receipt),
            "--owner-receipt-sha256", reservation_sha256]


def run_command(command: list[str], output: Path, cwd: Path = ROOT,
                env: dict | None = None, deadline_unix: float | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    command = list(map(str, command))
    atomic_json(output / "command.json", {"command": command, "cwd": str(cwd), "started_at_utc": utc_now()})
    started = time.time()
    with (output / "output.log").open("w") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        atomic_json(output / "process.json", {"pid": process.pid, "command": command,
                                               "started_at_utc": utc_now()})
        timeout = None if deadline_unix is None else max(0, deadline_unix - time.time())
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            code = process.returncode
        except BaseException:
            terminate_group(process)
            raise
    result = {"returncode": code, "timed_out": timed_out, "seconds": time.time() - started}
    atomic_json(output / "exit.json", result)
    if timed_out:
        raise TimeoutError(f"command exceeded its fixed deadline: {output}")
    if code != 0:
        raise RuntimeError(f"command failed with status {code}: {output}")
    return result


def validate_raw(raw: Path, plan: dict, bundle: dict, reservation: dict,
                 schedule_module) -> dict:
    records = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
    if len(records) != GAMES + 1:
        raise ValueError(f"raw schedule has {len(records) - 1} games; expected {GAMES}")
    header, rows = records[0], records[1:]
    if (header.get("games") != GAMES or header.get("master") != MASTER or
            header.get("planning_profile") != "alphazero-native-32a27ac-v1" or header.get("iterations") != 6400 or
            header.get("search") != "puct" or header.get("depth") != 64 or
            header.get("world_pool") != 3 or header.get("chance_universes") != 3 or
            header.get("dynamic_fpu") is not True or header.get("root_only") is not False):
        raise ValueError("raw schedule header differs from the registered campaign")
    diagnostic = header.get("opponent_search_diagnostic", {})
    if (diagnostic.get("profile") != PROFILE or diagnostic.get("active_num_mcts_sims") != AZ_SIMULATIONS or
            diagnostic.get("checkpoint_num_mcts_sims") != 800 or
            diagnostic.get("checkpoint_sha256") != AZ_CHECKPOINT_SHA256 or
            diagnostic.get("upstream_revision") != AZ_REVISION or
            diagnostic.get("validated_master") != MASTER or
            diagnostic.get("owner_receipt_sha256") != reservation["reservation_sha256"] or
            diagnostic.get("reservation") != {key: value for key, value in reservation.items()
                                               if key != "reservation_sha256"}):
        raise ValueError("raw schedule opponent identity or 6400 simulation receipt differs")
    external = header.get("external_config", {})
    expected_external = dict(plan["target"]["external_config"])
    expected_external["numMCTSSims"] = AZ_SIMULATIONS
    if external != expected_external:
        raise ValueError("raw AlphaZero config changed beyond the registered simulation count")
    if header.get("upstream_revision") != AZ_REVISION or header.get("upstream_checkpoint_sha256") != AZ_CHECKPOINT_SHA256:
        raise ValueError("raw AlphaZero source or checkpoint differs")
    if header.get("model_sha256") != bundle["descriptor_sha256"]:
        raise ValueError("raw schedule used a different candidate descriptor")
    for header_key, binary_name in (("policy_binary_sha256", "native_policy_worker"),
                                    ("strength_binary_sha256", "strength_worker")):
        if header.get(header_key) != bundle["binaries"][binary_name]["sha256"]:
            raise ValueError(f"raw schedule used a different {binary_name}")
    plan_path = raw.with_name("plan.json")
    schedule_plan = json.loads(plan_path.read_text())
    candidate = schedule_plan.get("candidate", {})
    if (candidate.get("model_sha256") != bundle["descriptor_sha256"] or
            candidate.get("policy_binary_sha256") != bundle["binaries"]["native_policy_worker"]["sha256"] or
            candidate.get("strength_binary_sha256") != bundle["binaries"]["strength_worker"]["sha256"] or
            schedule_plan.get("owner_receipt", {}).get("reservation_sha256") != reservation["reservation_sha256"] or
            schedule_plan.get("reservation") != {key: value for key, value in reservation.items()
                                                   if key != "reservation_sha256"}):
        raise ValueError("schedule plan does not bind the candidate, binaries, or master reservation")
    manifest_path = Path(reservation["bundle_manifest_path"])
    if (sha(manifest_path) != reservation["bundle_manifest_sha256"] or
            json.loads(manifest_path.read_text()).get("source_sha256") != reservation["source_sha256"]):
        raise ValueError("copied bundle manifest differs from the immutable reservation")
    raw_sources = header.get("source_sha256", {})
    for relative, digest in raw_sources.items():
        key = f"frozen-source:{relative}"
        if key not in bundle["sources"]:
            key = f"campaign-source:{relative}"
        if key not in bundle["sources"] or bundle["sources"][key]["sha256"] != digest:
            raise ValueError(f"raw metadata source hash differs for {relative}")

    seeds = schedule_module.validate_setup_seeds(MASTER, GAMES)
    expected_seed_hash = hashlib.sha256("".join(f"{seed}\n" for seed in seeds).encode()).hexdigest()
    if schedule_plan.get("opponent", {}).get("expected_setup_seed_sha256") != expected_seed_hash:
        raise ValueError("schedule plan setup-seed hash differs from the audited seed stream")
    if [row.get("index") for row in rows] != list(range(GAMES)):
        raise ValueError("raw rows are incomplete or unordered")
    if len({row["setup_seed"] for row in rows[::2]}) != GAMES // 2:
        raise ValueError("raw schedule contains duplicate paired setup seeds")
    for block, (a, b) in enumerate(zip(rows[::2], rows[1::2])):
        if (a.get("block") != block or b.get("block") != block or
                a.get("setup_seed") != b.get("setup_seed") or
                a.get("setup_seed") != seeds[block] or
                [a.get("rotation"), b.get("rotation")] != [0, 1]):
            raise ValueError("raw setup seeds differ from the audited paired seed stream")
    return {"header": header, "row_count": len(rows), "setup_seed_count": len(seeds),
            "raw_sha256": sha(raw)}


def run_campaign(output: Path, execute: bool, is_alive=pid_is_alive) -> dict:
    output = Path(output).resolve()
    if not execute:
        raise ValueError("campaign launch is disabled without --execute")
    if output != OUTPUT.resolve():
        raise ValueError("campaign output must use the registered new path")
    followup = json.loads(FOLLOWUP_PATH.read_text())
    plan = validate_followup_plan(followup)
    stopped = require_canonical_stopped(followup, is_alive)
    freeze_manifest = json.loads(FREEZE_PATH.read_text())
    decision = json.loads(DECISION_PATH.read_text())
    validate_build_inputs(followup, freeze_manifest, decision)
    checkpoint = CHECKPOINT.resolve(strict=True)
    if sha(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError("candidate checkpoint changed")
    if sha(PREFLIGHT) != SETUP_AUDIT_SHA256 or sha(EXCLUSIONS) != EXCLUSIONS_SHA256:
        raise ValueError("setup seed preflight changed")
    validation = json.loads(BUILD_VALIDATION.read_text())
    if any(item.get("status") != "passed" for item in validation.get("checks", [])):
        raise ValueError("dynamic-FPU binary validation did not pass every check")
    for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
        relative = f"local/research/sprint48/build-dynamic/release/examples/{name}"
        if sha(BUILD / name) != validation.get("binary_sha256", {}).get(relative):
            raise ValueError(f"dynamic-FPU binary differs from its passed validation receipt: {name}")
    upstream = validate_pinned_upstream(decision)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    deadline_unix = min(time.time() + DEADLINE_BUDGET_SECONDS, plan["deadline_unix"])
    schedule_deadline = deadline_unix - POSTPROCESS_RESERVE_SECONDS
    receipt = {"schema": "sprint48-opponent-search-campaign-v1", "status": "preparing",
               "profile": PROFILE, "owner_pid": os.getpid(), "output": str(output),
               "started_at_utc": utc_now(), "deadline_unix": deadline_unix,
               "schedule_deadline_unix": schedule_deadline,
               "games": GAMES, "master": MASTER, "opponent_simulations": AZ_SIMULATIONS,
               "candidate_search": expected_candidate_search(),
               "candidate_checkpoint_sha256": CHECKPOINT_SHA256,
               "canonical_job_stopped": stopped,
               "pinned_upstream": upstream,
               "original_decision_path": str(DECISION_PATH),
               "original_decision_sha256": sha(DECISION_PATH),
               "original_freeze_sha256": freeze_manifest["freeze_sha256"],
               "seed_consumed": False}
    atomic_json(output / "run.json", receipt)
    reservation_info = None
    schedule_process = None
    runtime = None
    failed = None
    try:
        bundle = copy_provenance(output, freeze_manifest, decision, checkpoint, BUILD)
        receipt["provenance"] = bundle
        receipt["binary_sha256"] = {name: row["sha256"] for name, row in bundle["binaries"].items()}
        atomic_json(output / "run.json", receipt)

        # Fail closed if this process does not use the study's MPS Python.
        expected_python = (ROOT / "local/strength/inference/bin/python").absolute()
        if Path(sys.executable).absolute() != expected_python:
            raise RuntimeError(f"run this driver with the pinned inference Python: {expected_python}")
        sys.path.insert(0, str(ROOT / "research/training_strategy"))
        from runtime import Runtime, command_run

        service_output = output / "service"
        runtime = Runtime([(13, output / "input/candidate.pt")], service_output,
                          port=PORT, device="mps", batch=BATCH, delay_ms=DELAY_MS)
        with runtime:
            descriptor = runtime.descriptors[13].resolve(strict=True)
            service_receipt = json.loads((service_output / "run.json").read_text())
            if service_receipt.get("pid") != runtime.service.pid:
                raise ValueError("owned service PID differs from Runtime receipt")
            service_check(output, output / "input/candidate.pt", descriptor)
            parity_dir = output / "parity-command"
            command_run([output / "binaries/transfer_parity", descriptor,
                         descriptor.with_name("parity.json"), "real"], parity_dir)
            parity_record = validate_parity(output, descriptor)
            bundle["descriptor_sha256"] = sha(descriptor)
            bundle["export_receipt_sha256"] = sha(descriptor.with_name("export.json"))
            bundle["parity"] = parity_record
            bundle["service_receipt_sha256"] = sha(service_output / "run.json")
            bundle["service_receipt"] = {"path": str(service_output / "run.json"),
                                         "sha256": bundle["service_receipt_sha256"]}
            bundle["runtime_source_sha256"] = sha(RUNTIME_SOURCE)
            bundle["exported_artifacts"] = {
                "model_pt": {"path": str(output / "service/13/model.pt"),
                             "sha256": sha(output / "service/13/model.pt")},
                "descriptor": {"path": str(descriptor), "sha256": sha(descriptor)},
                "export_receipt": {"path": str(descriptor.with_name("export.json")),
                                   "sha256": sha(descriptor.with_name("export.json"))},
                "parity_input": {"path": str(descriptor.with_name("parity.json")),
                                 "sha256": sha(descriptor.with_name("parity.json"))},
                "parity_receipt": parity_record,
            }
            bundle["service_receipt"] = {"path": str(service_output / "run.json"),
                                         "sha256": bundle["service_receipt_sha256"]}
            bundle["pinned_upstream"] = upstream
            write_bundle_manifest(output, freeze_manifest, bundle)
            receipt["provenance"] = bundle
            receipt["service"] = {"pid": runtime.service.pid, "port": PORT,
                                   "batch": BATCH, "delay_ms": DELAY_MS,
                                   "backend": "mps", "fast_entities": True,
                                   "receipt": str(service_output / "run.json"),
                                   "receipt_sha256": bundle["service_receipt_sha256"]}
            receipt["status"] = "preparing_schedule"
            atomic_json(output / "run.json", receipt)

            schedule_output = output / "schedule"
            reservation = build_reservation(schedule_output, bundle["descriptor_sha256"],
                                            descriptor, bundle)
            verify_bundle(reservation)
            # The output receipt has this immutable contract before it is reserved.
            receipt.update(status="running", schedule_output=str(schedule_output.resolve()),
                master=MASTER, games=GAMES, opponent_simulations=AZ_SIMULATIONS,
                candidate_search=expected_candidate_search(),
                candidate_checkpoint_sha256=CHECKPOINT_SHA256,
                candidate_descriptor_sha256=bundle["descriptor_sha256"],
                reservation=reservation, reservation_sha256=hash_value(reservation),
                service_pid=runtime.service.pid, seed_consumed=False)
            reservation_info = reserve_followup(FOLLOWUP_PATH, reservation)
            if reservation_info != receipt["reservation_sha256"]:
                raise RuntimeError("FOLLOWUP reservation digest differs from owner receipt")
            receipt["setup_seed_audit_path"] = str(PREFLIGHT)
            receipt["setup_seed_audit_sha256"] = SETUP_AUDIT_SHA256
            receipt["setup_exclusions_path"] = str(EXCLUSIONS)
            receipt["setup_exclusions_sha256"] = EXCLUSIONS_SHA256
            atomic_json(output / "run.json", receipt)
            command = schedule_command(schedule_output, descriptor, bundle["binaries"],
                                       reservation, reservation_info, output / "run.json")
            receipt["schedule_command"] = command
            receipt["schedule_started_at_utc"] = utc_now()
            receipt["schedule_deadline_unix"] = schedule_deadline
            atomic_json(output / "run.json", receipt)
            if time.time() >= schedule_deadline:
                raise TimeoutError("fixed follow-up deadline leaves no schedule time")
            with (output / "schedule-command.log").open("w") as log:
                schedule_process = subprocess.Popen(command, cwd=ROOT, stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True)
                # Mark seeds consumed immediately after successful Popen. Never retry this master.
                receipt["schedule_pid"] = schedule_process.pid
                receipt["seed_consumed"] = True
                receipt["status"] = "running"
                atomic_json(output / "run.json", receipt)
                update_reservation(FOLLOWUP_PATH, reservation_info, seed_consumed=True,
                    status="running", fields={"schedule_pid": schedule_process.pid,
                                               "seed_consumed_at_utc": utc_now()})
                remaining = schedule_deadline - time.time()
                try:
                    schedule_code = schedule_process.wait(timeout=max(0, remaining))
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate_group(schedule_process)
                    schedule_code = schedule_process.returncode
            receipt["schedule_exit"] = {"returncode": schedule_code, "timed_out": timed_out,
                "finished_at_utc": utc_now()}
            atomic_json(output / "run.json", receipt)
            if timed_out:
                raise TimeoutError("schedule exceeded its bounded deadline; records are retained")
            if schedule_code != 0:
                raise RuntimeError(f"schedule exited {schedule_code}; records are retained")
            schedule_result_path = output / "schedule-command.log"
            receipt["schedule_stdout_sha256"] = sha(schedule_result_path)
            raw = schedule_output / "games.jsonl"
            if not raw.is_file():
                raise ValueError("schedule completed without merged games.jsonl")
            sys.path.insert(0, str(Path(__file__).parent))
            import schedule as diagnostic_schedule
            raw_check = validate_raw(raw, decision, bundle | {"descriptor_sha256": bundle["descriptor_sha256"]},
                                     reservation | {"reservation_sha256": reservation_info},
                                     diagnostic_schedule)
            receipt["raw_validation"] = raw_check

        if runtime.service is not None and runtime.service.poll() is None:
            raise RuntimeError("owned MPS service did not stop after schedule completion")
        receipt["service_stopped"] = True
        for name, info in receipt["binary_sha256"].items():
            if sha(output / "binaries" / name) != info:
                raise RuntimeError(f"copied binary changed during the schedule: {name}")
        raw = output / "schedule/games.jsonl"
        post_deadline = deadline_unix
        run_command([sys.executable, str(REPLAY), str(raw), "--output", str(output / "replay.json"),
                     "--strength-binary", str(output / "binaries/strength_worker")],
                    output / "replay-command", deadline_unix=post_deadline)
        run_command([sys.executable, str(SUMMARIZE), str(raw), "--output", str(output / "summary.json")],
                    output / "summary-command", deadline_unix=post_deadline)
        run_command([sys.executable, str(EVIDENCE_SOURCE), str(raw), "--output", str(output / "evidence.json")],
                    output / "evidence-command", deadline_unix=post_deadline)
        replay = json.loads((output / "replay.json").read_text())
        summary = json.loads((output / "summary.json").read_text())
        evidence = json.loads((output / "evidence.json").read_text())
        if replay.get("checked_games") != GAMES or replay.get("raw_sha256") != sha(raw):
            raise ValueError("native replay did not verify every requested game")
        if summary.get("games") != GAMES or summary.get("statuses", {}).get("complete", 0) + summary.get("statuses", {}).get("no_legal_action", 0) != GAMES:
            raise ValueError("summary does not cover 1000 valid complete/no-action records")
        if summary.get("statuses", {}).get("no_legal_action", 0) > GAMES * 0.01:
            raise ValueError("no-action games exceed the registered one-percent limit")
        if evidence.get("games") != GAMES or evidence.get("evidence_rejections"):
            raise ValueError("paired evidence rejected the requested schedule")
        result = {"schema": "sprint48-opponent-search-result-v1", "status": "complete",
            "profile": PROFILE, "master": MASTER, "games": GAMES,
            "candidate_search": expected_candidate_search(),
            "opponent_simulations": AZ_SIMULATIONS,
            "scope": "Higher-search AlphaZero diagnostic. It is separate from the confirmed unchanged-AlphaZero800 proof and does not establish equal compute or a general ranking.",
            "raw_sha256": sha(raw), "replay_sha256": sha(output / "replay.json"),
            "summary_sha256": sha(output / "summary.json"),
            "evidence_sha256": sha(output / "evidence.json"),
            "statuses": summary.get("statuses"),
            "win_credit_bounds": evidence.get("all_requested_credit_bounds"),
            "conservative_paired_hoeffding95": evidence.get("conservative_hoeffding95_missing_envelope"),
            "caps_as_unknown_hoeffding95": evidence.get("caps_as_unknown_hoeffding95"),
            "evidence_rejections": evidence.get("evidence_rejections"),
            "output": str(output)}
        atomic_json(output / "result.json", result)
        receipt.update(status="complete", result_path=str(output / "result.json"),
                       result_sha256=sha(output / "result.json"), finished_at_utc=utc_now())
        atomic_json(output / "run.json", receipt)
        update_reservation(FOLLOWUP_PATH, reservation_info, seed_consumed=True,
                           status="complete", fields={"result_sha256": sha(output / "result.json"),
                                                       "finished_at_utc": utc_now()})
        print(json.dumps(result, sort_keys=True), flush=True)
        return result
    except BaseException as error:
        failed = error
        receipt.update(status="failed", failed_at_utc=utc_now(), error=repr(error),
                       error_traceback=traceback.format_exc())
        if schedule_process is not None:
            receipt["schedule_pid"] = schedule_process.pid
            receipt["seed_consumed"] = True
        atomic_json(output / "run.json", receipt)
        if reservation_info is not None:
            try:
                update_reservation(FOLLOWUP_PATH, reservation_info,
                    seed_consumed=bool(schedule_process is not None), status="failed",
                    fields={"error": repr(error)})
            except BaseException as update_error:
                receipt["followup_update_error"] = repr(update_error)
                receipt["followup_update_traceback"] = traceback.format_exc()
                atomic_json(output / "run.json", receipt)
        raise
    finally:
        if schedule_process is not None and schedule_process.poll() is None:
            terminate_group(schedule_process)
        if runtime is not None and runtime.service is not None and runtime.service.poll() is None:
            runtime.__exit__(None, None, None)


def terminate_group(process: subprocess.Popen, grace_seconds: int = 15) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except ProcessLookupError:
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--execute", action="store_true", help="start the reserved MPS schedule")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    try:
        if not args.execute:
            print(json.dumps({"status": "preflight_passed", **preflight(args.output)},
                             sort_keys=True, indent=2))
            return 0
        run_campaign(args.output, execute=True)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(json.dumps({"status": "failed", "error": repr(error)}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
