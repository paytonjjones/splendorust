#!/usr/bin/env python3
"""Recover completed diagnostic shards without replaying games.

This tool reads the original one-shot campaign. It writes merged raw data and
post-run checks to a new directory. It never retries a shard or edits RUN.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN = ROOT / "local/research/sprint48/opponent-search-6400"
PROFILE = "alphazero-native-search-budget-diagnostic-v1"
GAMES = 1000
WORKERS = 64
SIMULATIONS = 6400
DIAGNOSTIC_SCHEDULE = Path(__file__).with_name("schedule.py").resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def load_diagnostic_schedule():
    native = ROOT / "benchmarks/strength/native"
    if str(native) not in sys.path:
        sys.path.insert(0, str(native))
    spec = importlib.util.spec_from_file_location("sprint48_opponent_search_schedule", DIAGNOSTIC_SCHEDULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the diagnostic scheduler")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Treat a zombie as stopped. On macOS `ps` reports Z for a zombie.
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True, text=True, check=False)
    state = result.stdout.strip()
    return bool(state) and not state.startswith("Z")


def assert_no_shard_processes(schedule_dir: Path) -> None:
    result = subprocess.run(["ps", "-axo", "pid=,command="],
        capture_output=True, text=True, check=True)
    marker = str(schedule_dir.resolve())
    active = []
    for line in result.stdout.splitlines():
        if marker in line and "shard-" in line and "recover_completion.py" not in line:
            active.append(line.strip())
    if active:
        raise RuntimeError("native shard processes are still active: " + "; ".join(active[:3]))


def assert_campaign_stopped(run_dir: Path, receipt: dict) -> None:
    if receipt.get("status") not in {"failed", "complete"}:
        raise ValueError("campaign driver is not in a stopped terminal state")
    if receipt.get("seed_consumed") is not True:
        raise ValueError("the registered setup stream was not consumed by the original schedule")
    service = receipt.get("service", {})
    pids = {"driver": receipt.get("owner_pid"), "schedule": receipt.get("schedule_pid"),
        "service": receipt.get("service_pid", service.get("pid"))}
    running = [f"{name}={pid}" for name, pid in pids.items() if pid_running(pid)]
    if running:
        raise RuntimeError("campaign processes are still active: " + ", ".join(running))
    assert_no_shard_processes(run_dir / "schedule")


def wait_until_stopped(run_dir: Path, *, load_receipt=read_json,
                       stopped_check=assert_campaign_stopped,
                       sleep=time.sleep, now=time.time) -> dict:
    """Wait through normal live states; reject a bad terminal receipt."""
    while True:
        receipt = load_receipt(run_dir / "run.json")
        if receipt.get("status") in {"preparing", "preparing_schedule", "reserved", "running"}:
            if now() >= receipt.get("deadline_unix", 0):
                raise TimeoutError("campaign deadline passed before all workers stopped")
            sleep(10)
            continue
        try:
            stopped_check(run_dir, receipt)
        except RuntimeError:
            if now() >= receipt.get("deadline_unix", 0):
                raise TimeoutError("campaign deadline passed before all workers stopped")
            sleep(10)
            continue
        return receipt


def expected_decision_config(receipt: dict) -> dict:
    path = Path(receipt["original_decision_path"]).resolve(strict=True)
    if sha(path) != receipt.get("original_decision_sha256"):
        raise ValueError("pinned decision receipt changed after the campaign")
    decision = read_json(path)
    if decision.get("status") != "confirmed_decisive_native_win":
        raise ValueError("pinned decision no longer records the confirmed baseline")
    config = decision.get("target", {}).get("external_config")
    if not isinstance(config, dict) or config.get("numMCTSSims") != 800:
        raise ValueError("pinned external configuration is not the AlphaZero800 baseline")
    return config


def validate_opponent_config(header: dict, expected_config: dict, plan: dict,
                             reservation_sha256: str, reservation: dict) -> None:
    diagnostic = header.get("opponent_search_diagnostic", {})
    if (expected_config.get("numMCTSSims") != 800
            or header.get("external_config") != expected_config
            or diagnostic.get("checkpoint_num_mcts_sims") != 800
            or diagnostic.get("active_num_mcts_sims") != SIMULATIONS
            or diagnostic.get("checkpoint_sha256") != plan["opponent"].get("checkpoint_sha256")
            or diagnostic.get("upstream_revision") != plan["opponent"].get("upstream_revision")
            or diagnostic.get("owner_receipt_sha256") != reservation_sha256
            or diagnostic.get("reservation") != reservation
            or header.get("upstream_checkpoint_sha256") != plan["opponent"].get("checkpoint_sha256")
            or header.get("upstream_revision") != plan["opponent"].get("upstream_revision")):
        raise ValueError("header does not bind the unchanged 800 checkpoint config and active 6400 diagnostic")


def validate_header_sources(header: dict, reservation: dict) -> None:
    observed = header.get("source_sha256")
    expected = reservation.get("source_sha256")
    if not isinstance(observed, dict) or not isinstance(expected, dict) or not observed:
        raise ValueError("header or reservation has no source hash map")
    for relative, source_hash in observed.items():
        if expected.get(relative) != source_hash:
            raise ValueError(f"header source hash differs from reserved bundle: {relative}")


def validate_candidate_artifacts(plan: dict, reservation: dict) -> None:
    candidate = plan.get("candidate", {})
    binaries = reservation.get("candidate_artifacts", {}).get("binaries", {})
    expected = {
        "model": (candidate.get("model_path"), candidate.get("model_sha256"),
            reservation.get("candidate_descriptor_path"), reservation.get("candidate_descriptor_sha256")),
        "policy binary": (candidate.get("policy_binary_path"), candidate.get("policy_binary_sha256"),
            binaries.get("native_policy_worker", {}).get("path"),
            binaries.get("native_policy_worker", {}).get("sha256")),
        "strength binary": (candidate.get("strength_binary_path"), candidate.get("strength_binary_sha256"),
            binaries.get("strength_worker", {}).get("path"),
            binaries.get("strength_worker", {}).get("sha256")),
    }
    for label, (path, file_hash, reserved_path, reserved_hash) in expected.items():
        if path != reserved_path or file_hash != reserved_hash:
            raise ValueError(f"schedule plan {label} differs from the owner reservation")


def validate_plan_profile(plan: dict, reservation: dict, receipt: dict) -> None:
    expected = {"algorithm": "puct", "iterations": SIMULATIONS,
        "depth": 64, "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True}
    if reservation.get("candidate_search") != expected:
        raise ValueError("reservation candidate search differs from the fixed diagnostic profile")
    candidate = plan.get("candidate", {})
    candidate_fields = {"algorithm": candidate.get("search"),
        "iterations": candidate.get("iterations"), "depth": candidate.get("depth"),
        "world_pool": candidate.get("world_pool"),
        "chance_universes": candidate.get("chance_universes"),
        "dynamic_fpu": candidate.get("dynamic_fpu")}
    if candidate_fields != expected or candidate.get("root_only") is not False:
        raise ValueError("schedule candidate search differs from the owner reservation")
    opponent = plan.get("opponent", {})
    pinned = receipt.get("pinned_upstream", {})
    if (opponent.get("upstream_revision") != pinned.get("revision")
            or opponent.get("checkpoint_sha256") != pinned.get("checkpoint_sha256")):
        raise ValueError("schedule opponent differs from the pinned owner receipt")


def verified_live_source(relative: str, reservation: dict, manifest: dict) -> Path:
    live = ROOT / relative
    expected = reservation.get("source_sha256", {}).get(relative)
    if expected is None or sha(live) != expected:
        raise ValueError(f"live post-processing source differs from registered hash: {relative}")
    copied = manifest.get("files", {}).get("sources", {})
    choices = [item for key, item in copied.items() if key.endswith(":" + relative)]
    if not choices or any(item.get("sha256") != expected for item in choices):
        raise ValueError(f"registered copied source differs from its source hash: {relative}")
    return live


def validate_reservation(run_dir: Path, receipt: dict, plan: dict) -> dict:
    reservation = receipt.get("reservation")
    reservation_hash = receipt.get("reservation_sha256")
    if not isinstance(reservation, dict) or digest(reservation) != reservation_hash:
        raise ValueError("owner receipt has no valid fixed reservation")
    if receipt.get("status") not in {"failed", "complete"} or receipt.get("seed_consumed") is not True:
        raise ValueError("owner receipt is not a consumed stopped campaign")
    expected = {"profile": PROFILE, "master": 17_792_000_000, "games": GAMES,
        "opponent_simulations": SIMULATIONS,
        "schedule_output": str((run_dir / "schedule").resolve())}
    if any(reservation.get(key) != value for key, value in expected.items()):
        raise ValueError("reservation differs from the fixed diagnostic campaign")
    if plan.get("reservation") != reservation:
        raise ValueError("schedule plan reservation differs from owner receipt")
    owner_plan = plan.get("owner_receipt", {})
    if (owner_plan.get("reservation") != reservation
            or owner_plan.get("reservation_sha256") != reservation_hash
            or Path(owner_plan.get("path", "")).resolve() != (run_dir / "run.json").resolve()):
        raise ValueError("schedule plan owner receipt binding differs")
    if (plan.get("profile") != PROFILE or plan.get("master") != expected["master"]
            or plan.get("games") != GAMES or plan.get("workers") != WORKERS):
        raise ValueError("schedule plan is not the registered fixed 64-shard campaign")
    validate_plan_profile(plan, reservation, receipt)
    validate_candidate_artifacts(plan, reservation)
    if (reservation.get("bundle_manifest_sha256") != sha(Path(reservation["bundle_manifest_path"]))):
        raise ValueError("registered copied bundle manifest changed")
    manifest = read_json(Path(reservation["bundle_manifest_path"]))
    if manifest.get("source_sha256") != reservation.get("source_sha256"):
        raise ValueError("copied bundle source hashes differ from reservation")
    source_rows = manifest.get("files", {}).get("sources", {})
    observed = {}
    for key, item in source_rows.items():
        if not (key.startswith("frozen-source:") or key.startswith("campaign-source:")):
            raise ValueError(f"unrecognized copied source key: {key}")
        source_path = Path(item.get("path", "")).resolve(strict=True)
        if sha(source_path) != item.get("sha256"):
            raise ValueError(f"copied source changed: {key}")
        relative = key.split(":", 1)[1]
        if relative in observed and observed[relative] != item["sha256"]:
            raise ValueError(f"frozen and campaign source copies differ: {relative}")
        observed[relative] = item["sha256"]
    if observed != reservation.get("source_sha256"):
        raise ValueError("copied source rows do not match the flat source hash map")
    binaries = reservation.get("candidate_artifacts", {}).get("binaries", {})
    for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
        info = binaries.get(name, {})
        binary_path = Path(info.get("path", "")).resolve(strict=True)
        if sha(binary_path) != info.get("sha256"):
            raise ValueError(f"registered copied binary changed: {name}")
    service = reservation.get("service", {})
    if reservation.get("candidate_artifacts", {}).get("service") != service:
        raise ValueError("nested and top-level service artifact receipts differ")
    required_service = {"backend": "mps", "batch": 32, "delay_ms": 1,
        "port": 19760, "fast_entities": True, "slot": 13}
    if any(service.get(key) != value for key, value in required_service.items()):
        raise ValueError("registered service settings differ from the fixed diagnostic profile")
    for path_key, hash_key in (("checkpoint_path", "checkpoint_sha256"),
            ("model_pt_path", "model_pt_sha256"), ("descriptor_path", "descriptor_sha256"),
            ("export_receipt_path", "export_receipt_sha256"),
            ("service_receipt_path", "service_receipt_sha256"),
            ("parity_input_path", "parity_input_sha256"),
            ("parity_receipt_path", "parity_receipt_sha256")):
        artifact_path = Path(service[path_key]).resolve(strict=True)
        if sha(artifact_path) != service[hash_key]:
            raise ValueError(f"registered service artifact changed: {path_key}")
    if (service["checkpoint_path"] != reservation.get("candidate_checkpoint_path")
            or service["checkpoint_sha256"] != reservation.get("candidate_checkpoint_sha256")
            or service["descriptor_path"] != reservation.get("candidate_descriptor_path")
            or service["descriptor_sha256"] != reservation.get("candidate_descriptor_sha256")):
        raise ValueError("candidate and service checkpoint/descriptor identities differ")
    service_receipt = read_json(Path(service["service_receipt_path"]))
    service_command = service_receipt.get("command", [])
    required_args = {"--port": "19760", "--device": "mps", "--batch": "32", "--delay-ms": "1"}
    if any(flag not in service_command or service_command.index(flag) + 1 >= len(service_command)
            or service_command[service_command.index(flag) + 1] != value
            for flag, value in required_args.items()) or "--fast-entities" not in service_command:
        raise ValueError("owned inference service command differs from the reserved settings")
    if (service_receipt.get("pid") != receipt.get("service", {}).get("pid")
            or service_receipt.get("batch") != 32 or service_receipt.get("delay_ms") != 1
            or service_receipt.get("models", {}).get("13", {}).get("checkpoint_sha256")
                != reservation.get("candidate_checkpoint_sha256")
            or service_receipt.get("models", {}).get("13", {}).get("descriptor_sha256")
                != reservation.get("candidate_descriptor_sha256")):
        raise ValueError("owned inference service receipt differs from the reserved model or settings")
    export = read_json(Path(service["export_receipt_path"]))
    if (export.get("checkpoint_sha256") != reservation.get("candidate_checkpoint_sha256")
            or export.get("descriptor_sha256") != reservation.get("candidate_descriptor_sha256")):
        raise ValueError("export receipt does not bind the registered checkpoint and descriptor")
    parity = read_json(Path(service["parity_receipt_path"]))
    exit_receipt = parity.get("exit", {})
    tolerance = parity.get("output_tolerance", 0)
    real_tolerance = parity.get("real_logit_tolerance", 0)
    if (exit_receipt.get("returncode") != 0
            or parity.get("all_inputs_max_logit_error", float("inf")) > tolerance
            or parity.get("masked_policy_and_value_max_error", float("inf")) > tolerance
            or parity.get("real_initial_board_max_logit_error", float("inf")) > real_tolerance):
        raise ValueError("registered native transfer parity receipt did not pass")
    relative = "research/sprint48/opponent_search/run_campaign.py"
    campaign_row = source_rows.get(f"campaign-source:{relative}")
    if not campaign_row or sha(ROOT / relative) != campaign_row.get("sha256"):
        raise ValueError("campaign bundle validator differs from the copied source")
    if str(ROOT / "research/sprint48/opponent_search") not in sys.path:
        sys.path.insert(0, str(ROOT / "research/sprint48/opponent_search"))
    import run_campaign
    run_campaign.verify_bundle(reservation)
    return reservation


def expected_shard_counts() -> list[tuple[int, int]]:
    blocks = GAMES // 2
    base, extra = divmod(blocks, WORKERS)
    result, offset = [], 0
    for index in range(WORKERS):
        count = base + int(index < extra)
        result.append((offset, count))
        offset += count
    assert offset == blocks
    return result


def validate_shards(run_dir: Path, receipt: dict, plan: dict,
                    expected_seeds: list[int]) -> tuple[dict, list[dict]]:
    schedule_dir = run_dir / "schedule"
    execution = read_json(schedule_dir / "execution.json")
    executions = execution.get("executions", [])
    if (len(executions) != WORKERS
            or sorted(row.get("worker") for row in executions) != list(range(WORKERS))
            or any(row.get("exit") != 0 for row in executions)):
        raise ValueError("all original shard processes must have successful completion receipts")
    expected = expected_shard_counts()
    headers, all_rows = [], []
    decision_config = expected_decision_config(receipt)
    for shard, (offset, paired_count) in enumerate(expected):
        path = schedule_dir / f"shard-{shard:02}.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not records:
            raise ValueError(f"shard {shard} is empty")
        header, rows = records[0], records[1:]
        expected_game_count = paired_count * 2
        if (header.get("games") != expected_game_count or header.get("offset_block") != offset
                or header.get("master") != plan["master"] or header.get("iterations") != SIMULATIONS
                or header.get("model_sha256") != plan["candidate"].get("model_sha256")
                or header.get("policy_binary_sha256") != plan["candidate"].get("policy_binary_sha256")
                or header.get("strength_binary_sha256") != plan["candidate"].get("strength_binary_sha256")
                or header.get("iterations") != plan["candidate"].get("iterations")
                or header.get("depth") != plan["candidate"].get("depth")
                or header.get("world_pool") != plan["candidate"].get("world_pool")
                or header.get("chance_universes") != plan["candidate"].get("chance_universes")
                or header.get("dynamic_fpu") != plan["candidate"].get("dynamic_fpu")
                or header.get("search") != plan["candidate"].get("search")
                or header.get("root_only") != plan["candidate"].get("root_only")
                or header.get("source_sha256", {}).get("research/sprint48/opponent_search/schedule.py")
                    != plan.get("wrapper_sha256", {}).get("schedule.py")):
            raise ValueError(f"shard {shard} header differs from the frozen 800-checkpoint/6400-active profile")
        validate_header_sources(header, receipt["reservation"])
        validate_candidate_artifacts(plan, receipt["reservation"])
        validate_opponent_config(header, decision_config, plan,
            receipt.get("reservation_sha256"), receipt.get("reservation"))
        diagnostic = header["opponent_search_diagnostic"]
        if (diagnostic.get("profile") != PROFILE
                or header.get("source_sha256", {}).get("research/sprint48/opponent_search/run.py")
                    != diagnostic.get("wrapper_sha256")):
            raise ValueError(f"shard {shard} diagnostic wrapper provenance differs")
        if len(rows) != expected_game_count:
            raise ValueError(f"shard {shard} row count differs from its fixed plan")
        expected_indices = list(range(offset * 2, (offset + paired_count) * 2))
        if [row.get("index") for row in rows] != expected_indices:
            raise ValueError(f"shard {shard} game indices differ from its fixed block range")
        headers.append(header)
        all_rows.extend(rows)

    from collections import Counter
    common_keys = ("external_config", "source_sha256", "upstream_revision",
        "upstream_checkpoint_sha256", "model_sha256", "policy_binary_sha256",
        "strength_binary_sha256", "iterations", "depth", "world_pool", "chance_universes",
        "dynamic_fpu", "search", "root_only", "opponent_search_diagnostic")
    for key in common_keys:
        if any(header.get(key) != headers[0].get(key) for header in headers[1:]):
            raise ValueError(f"shard headers differ in shared field {key}")
    if len(all_rows) != GAMES:
        raise ValueError("original shards do not contain exactly 1000 games")
    all_rows.sort(key=lambda row: row["index"])
    if [row["index"] for row in all_rows] != list(range(GAMES)):
        raise ValueError("merged game indices are incomplete")
    if expected_seeds and len(expected_seeds) != GAMES // 2:
        raise ValueError("audited setup seed list does not cover 500 blocks")
    for block, (first, second) in enumerate(zip(all_rows[::2], all_rows[1::2])):
        if (first.get("block") != block or second.get("block") != block
                or first.get("rotation") != 0 or second.get("rotation") != 1
                or first.get("setup_seed") != second.get("setup_seed")
                or (expected_seeds and first.get("setup_seed") != expected_seeds[block])):
            raise ValueError(f"paired setup, rotation, or seed differs at block {block}")
        if first.get("status") not in {"complete", "no_legal_action"} or second.get("status") not in {"complete", "no_legal_action"}:
            raise ValueError(f"block {block} contains invalid or decision-limit outcome")
    return headers[0], all_rows


def run_checked(command: list[str], deadline_unix: float) -> None:
    remaining = deadline_unix - time.time()
    if remaining <= 0:
        raise TimeoutError("original campaign deadline passed before post-run checks")
    try:
        subprocess.run(command, cwd=ROOT, check=True, timeout=remaining)
    except subprocess.TimeoutExpired as error:
        raise TimeoutError("post-run command reached the campaign deadline; partial files remain") from error


def recover(run_dir: Path, output_dir: Path) -> dict:
    run_dir = run_dir.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("recovery output already exists; choose a new directory")
    if output_dir == run_dir or run_dir in output_dir.parents:
        raise ValueError("recovery output must be outside the original campaign")
    receipt = read_json(run_dir / "run.json")
    assert_campaign_stopped(run_dir, receipt)
    plan = read_json(run_dir / "schedule/plan.json")
    reservation = validate_reservation(run_dir, receipt, plan)

    # Use the same hash-bound seed auditor that authorized the original schedule.
    scheduler = load_diagnostic_schedule()
    seeds = [scheduler.stream(reservation["master"], "setup", block)
        for block in range(GAMES // 2)]
    if hashlib.sha256("".join(f"{seed}\n" for seed in seeds).encode()).hexdigest() != plan["opponent"].get("expected_setup_seed_sha256"):
        raise ValueError("setup-seed stream differs from the schedule plan")
    # This also rechecks the independently pinned preflight/exclusion files.
    if scheduler.validate_setup_seeds(reservation["master"], GAMES) != seeds:
        raise ValueError("setup-seed preflight differs from the schedule plan")
    header, rows = validate_shards(run_dir, receipt, plan, seeds)

    output_dir.mkdir(parents=True)
    raw_path = output_dir / "games.jsonl"
    merged = dict(header, games=GAMES, offset_block=0, workers=WORKERS,
        recovered_from_shards=True,
        original_schedule_plan_sha256=sha(run_dir / "schedule/plan.json"),
        original_owner_receipt_sha256=receipt["reservation_sha256"])
    with raw_path.open("x") as stream:
        stream.write(json.dumps(merged) + "\n")
        for row in rows:
            stream.write(json.dumps(row) + "\n")

    manifest = read_json(Path(reservation["bundle_manifest_path"]))
    python = ROOT / "local/strength/inference/bin/python"
    strength = Path(plan["candidate"]["strength_binary_path"]).resolve(strict=True)
    replay = verified_live_source("benchmarks/strength/native/replay.py", reservation, manifest)
    summarize = verified_live_source("benchmarks/strength/native/summarize.py", reservation, manifest)
    verified_live_source("benchmarks/strength/native/upstream.py", reservation, manifest)
    evidence = verified_live_source("research/sprint48/evidence.py", reservation, manifest)
    deadline = receipt.get("deadline_unix")
    if not isinstance(deadline, (int, float)) or deadline <= 0:
        raise ValueError("owner receipt has no finite recovery deadline")
    run_checked([str(python), str(replay), str(raw_path), "--output", str(output_dir / "replay.json"),
        "--strength-binary", str(strength)], deadline)
    run_checked([str(python), str(summarize), str(raw_path), "--output", str(output_dir / "summary.json")], deadline)
    run_checked([str(python), str(evidence), str(raw_path), "--output", str(output_dir / "evidence.json")], deadline)
    replay_result = read_json(output_dir / "replay.json")
    summary = read_json(output_dir / "summary.json")
    evidence_result = read_json(output_dir / "evidence.json")
    raw_hash = sha(raw_path)
    if (replay_result.get("checked_games") != GAMES or replay_result.get("raw_sha256") != raw_hash
            or summary.get("games") != GAMES or evidence_result.get("games") != GAMES
            or evidence_result.get("raw_sha256") != raw_hash):
        raise ValueError("replay or regenerated evidence does not bind all 1000 original games")
    statuses = evidence_result.get("statuses", {})
    if (evidence_result.get("evidence_rejections")
            or statuses.get("invalid", 0) or statuses.get("decision_limit", 0)
            or statuses.get("no_legal_action", 0) > GAMES * 0.01):
        raise ValueError("fresh evidence has invalid, decision-limit, or excess no-action outcomes")
    report = {"schema": "sprint48-opponent-search-recovery-v1", "status": "complete",
        "profile": PROFILE, "games": GAMES, "master": reservation["master"],
        "checkpoint_external_config_num_mcts_sims": 800,
        "diagnostic_active_num_mcts_sims": SIMULATIONS,
        "original_run_status": receipt["status"], "original_seed_consumed": True,
        "original_plan_sha256": sha(run_dir / "schedule/plan.json"),
        "original_reservation_sha256": receipt["reservation_sha256"],
        "raw_sha256": raw_hash, "replay_sha256": sha(output_dir / "replay.json"),
        "summary_sha256": sha(output_dir / "summary.json"),
        "evidence_sha256": sha(output_dir / "evidence.json"),
        "statuses": summary.get("statuses"), "evidence_rejections": evidence_result.get("evidence_rejections"),
        "credit_bounds": evidence_result.get("all_requested_credit_bounds"),
        "paired_hoeffding95": evidence_result.get("conservative_hoeffding95_missing_envelope"),
        "caps_as_unknown_hoeffding95": evidence_result.get("caps_as_unknown_hoeffding95"),
        "replay_checked_transitions": replay_result.get("checked_transitions"),
        "output": str(output_dir)}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recover", action="store_true",
        help="write merged raw data and post-run checks into the new output directory")
    parser.add_argument("--wait", action="store_true",
        help="with --recover, wait for the original campaign to stop before recovery")
    args = parser.parse_args()
    if args.wait and not args.recover:
        parser.error("--wait requires --recover")
    if args.wait:
        run_dir = args.run.resolve(strict=True)
        wait_until_stopped(run_dir)
    if args.recover:
        result = recover(args.run, args.output)
    else:
        # Default mode validates readiness and does not create files.
        run_dir = args.run.resolve(strict=True)
        receipt = read_json(run_dir / "run.json")
        assert_campaign_stopped(run_dir, receipt)
        plan = read_json(run_dir / "schedule/plan.json")
        reservation = validate_reservation(run_dir, receipt, plan)
        scheduler = load_diagnostic_schedule()
        seeds = scheduler.validate_setup_seeds(reservation["master"], GAMES)
        header, rows = validate_shards(run_dir, receipt, plan, seeds)
        result = {"status": "ready", "read_only": True, "games": len(rows),
            "checkpoint_num_mcts_sims": header["external_config"]["numMCTSSims"],
            "diagnostic_active_num_mcts_sims": header["opponent_search_diagnostic"]["active_num_mcts_sims"],
            "run": str(run_dir), "output_not_created": str(args.output)}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
