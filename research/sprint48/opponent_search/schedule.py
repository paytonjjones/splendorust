#!/usr/bin/env python3
"""Schedule fixed paired native games for the stronger-AZ diagnostic profile."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "benchmarks/strength/native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
from upstream import DEFAULT_STRENGTH_BINARY, PIN, SOURCE, sha
from upstream import stream

PROFILE = "alphazero-native-search-budget-diagnostic-v1"
RUN_PATH = ROOT / "research/sprint48/RUN.json"
PLAN_PATH = ROOT / "research/sprint48/PLAN.json"
PYTHON = ROOT / "local/strength/inference/bin/python"
RUNNER = Path(__file__).with_name("run.py").resolve()
SETUP_AUDIT = ROOT / "local/research/sprint48/opponent-search-preflight/setup-audit.json"
EXCLUDED_SETUP_IDS = ROOT / "local/research/sprint48/opponent-search-preflight/excluded-setup-ids.txt"
SETUP_AUDIT_SHA256 = "a92ca6b397c9cffd6d0a24f9a7984377254fc5d0e0055076beffdbbdbbf91b0a"
EXCLUDED_SETUP_IDS_SHA256 = "6f5e7a9f13efde03bd589692f89a04af134ef5944a5e213f90f2bc51044a8a13"


def validate_setup_seeds(master: int, games: int, audit_path: Path = SETUP_AUDIT,
                         excluded_path: Path = EXCLUDED_SETUP_IDS) -> list[int]:
    if sha(audit_path) != SETUP_AUDIT_SHA256 or sha(excluded_path) != EXCLUDED_SETUP_IDS_SHA256:
        raise ValueError("hash-bound setup-seed preflight files differ")
    audit = json.loads(audit_path.read_text())
    if (audit.get("schema") != "opponent-search-setup-audit-v1"
            or audit.get("proposed_master") != master
            or audit.get("games") < games
            or audit.get("paired_blocks") != audit.get("games", 0) // 2
            or audit.get("full64_overlap") != 0 or audit.get("low32_overlap") != 0
            or audit.get("planned_low32_unique") != audit.get("paired_blocks")):
        raise ValueError("setup-seed preflight does not authorize this master and game count")
    excluded = {int(line) for line in excluded_path.read_text().splitlines() if line.strip()}
    if len(excluded) != audit.get("excluded_setup_ids"):
        raise ValueError("excluded setup-ID count differs from hash-bound preflight")
    seeds = [stream(master, "setup", block) for block in range(games // 2)]
    excluded_low32 = {seed & 0xFFFFFFFF for seed in excluded}
    if len(set(seeds)) != len(seeds) or len({seed & 0xFFFFFFFF for seed in seeds}) != len(seeds):
        raise ValueError("diagnostic setup seeds are not unique")
    if any(seed in excluded for seed in seeds) or any((seed & 0xFFFFFFFF) in excluded_low32 for seed in seeds):
        raise ValueError("diagnostic setup seed overlaps the preflight exclusion set")
    return seeds


def fresh_master(master: int, games: int, output: Path) -> list[int]:
    run = json.loads(RUN_PATH.read_text())
    plan = json.loads(PLAN_PATH.read_text())
    used = {int(row["master"]) for row in run.get("consumed_trials", [])}
    used.update(int(row["master"]) for row in run.get("failed_attempts", []) if row.get("master") is not None)
    final = run.get("final_campaign", {})
    reserved = {run.get("final_master"), final.get("master"),
        plan.get("seeds", {}).get("final_external", {}).get("master"),
        plan.get("seeds", {}).get("final_canonical", {}).get("master")}
    if master in used:
        raise ValueError("diagnostic master was already used by a recorded trial")
    if master in reserved:
        raise ValueError("diagnostic master is sealed for a final campaign")
    seeds = validate_setup_seeds(master, games)
    final_output = final.get("output")
    if final_output and (output == Path(final_output).resolve()
                         or Path(final_output).resolve() in output.parents):
        raise ValueError("diagnostic output cannot be inside the final campaign output")
    if not output.is_absolute():
        raise ValueError("output must be an absolute path")
    return seeds


def build_command(args, offset: int, count: int, output: Path) -> list[str]:
    command = [str(PYTHON), str(RUNNER), "--alphazero-simulations", str(args.alphazero_simulations),
        "--owner-receipt", str(args.owner_receipt.resolve()),
        "--owner-receipt-sha256", args.owner_receipt_sha256,
        "--games", str(count), "--master", str(args.master), "--offset-block", str(offset),
        "--iterations", str(args.iterations), "--depth", str(args.depth),
        "--world-pool", str(args.world_pool), "--chance-universes", str(args.chance_universes),
        "--gumbel-max-considered", str(args.gumbel_max_considered), "--search", args.search,
        "--policy-binary", str(args.policy_binary), "--strength-binary", str(args.strength_binary),
        "--output", str(output)]
    if args.dynamic_fpu:
        command.append("--dynamic-fpu")
    if args.root_only:
        command.append("--root-only")
    if args.model:
        command += ["--model", str(args.model)]
    return command


def canonical_digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_manifest_sources(manifest: dict, source_hashes: dict) -> None:
    if manifest.get("source_sha256") != source_hashes or not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("bundle manifest source hashes differ from reservation")
    rows = manifest.get("files", {}).get("sources", {})
    if not isinstance(rows, dict):
        raise ValueError("bundle manifest has no copied source inventory")
    for relative, digest in source_hashes.items():
        matches = [row for key, row in rows.items() if key.endswith(":" + relative)]
        if not matches or any(row.get("sha256") != digest for row in matches):
            raise ValueError(f"bundle manifest does not bind copied source: {relative}")
        for item in matches:
            path = Path(item.get("path", "")).resolve(strict=True)
            if sha(path) != digest:
                raise ValueError(f"copied source hash differs: {relative}")


def validate_owner(owner: dict, receipt_path: Path, supplied_digest: str, output: Path,
                   master: int, games: int, alpha_sims: int, candidate: dict,
                   candidate_checkpoint_sha256: str, candidate_descriptor_sha256: str) -> None:
    reservation = owner.get("reservation")
    digest = owner.get("reservation_sha256")
    expected = {"profile": "alphazero-native-search-budget-diagnostic-v1",
        "master": master, "games": games, "schedule_output": str(output),
        "opponent_simulations": alpha_sims, "candidate_search": candidate,
        "candidate_checkpoint_sha256": candidate_checkpoint_sha256,
        "candidate_descriptor_sha256": candidate_descriptor_sha256}
    if (not isinstance(reservation, dict)
            or any(reservation.get(key) != value for key, value in expected.items())
            or digest != supplied_digest or canonical_digest(reservation) != digest
            or owner.get("schema") != "sprint48-opponent-search-campaign-v1"
            or owner.get("status") != "running"
            or (owner.get("receipt_path") is not None
                and Path(receipt_path).resolve() != Path(owner["receipt_path"]).resolve())):
        raise ValueError("owner receipt does not reserve these diagnostic settings and output")


def validate_bundle(reservation: dict, model: Path, policy: Path, strength: Path) -> None:
    def check(path_value: str, expected: str, label: str) -> Path:
        path = Path(path_value).resolve(strict=True)
        if sha(path) != expected:
            raise ValueError(f"diagnostic {label} hash differs: {path}")
        return path

    checkpoint = check(reservation["candidate_checkpoint_path"],
        reservation["candidate_checkpoint_sha256"], "checkpoint")
    descriptor = check(reservation["candidate_descriptor_path"],
        reservation["candidate_descriptor_sha256"], "descriptor")
    if descriptor != model.resolve(strict=True):
        raise ValueError("runner model descriptor differs from owner reservation")
    artifacts = reservation["candidate_artifacts"]
    binaries = artifacts["binaries"]
    for name, expected_path in (("native_policy_worker", policy), ("strength_worker", strength)):
        path = check(binaries[name]["path"], binaries[name]["sha256"], name)
        if path != expected_path.resolve(strict=True):
            raise ValueError(f"runner {name} differs from owner reservation")
    check(binaries["transfer_parity"]["path"], binaries["transfer_parity"]["sha256"], "transfer_parity")

    service = reservation["service"]
    required_config = {"backend": "mps", "batch": 32, "delay_ms": 1,
        "port": 19760, "fast_entities": True, "slot": 13}
    if any(service.get(key) != value for key, value in required_config.items()):
        raise ValueError("diagnostic inference service settings differ from the registered profile")
    service_paths = (("checkpoint_path", "checkpoint_sha256"),
        ("model_pt_path", "model_pt_sha256"), ("descriptor_path", "descriptor_sha256"),
        ("export_receipt_path", "export_receipt_sha256"),
        ("service_receipt_path", "service_receipt_sha256"),
        ("parity_receipt_path", "parity_receipt_sha256"))
    for path_key, hash_key in service_paths:
        path = check(service[path_key], service[hash_key], f"service {path_key}")
        if path_key == "descriptor_path" and path != descriptor:
            raise ValueError("service descriptor differs from candidate descriptor")
        if path_key == "checkpoint_path" and path != checkpoint:
            raise ValueError("service checkpoint differs from candidate checkpoint")
    export = json.loads(Path(service["export_receipt_path"]).read_text())
    if (export.get("checkpoint_sha256") != reservation["candidate_checkpoint_sha256"]
            or export.get("descriptor_sha256") != reservation["candidate_descriptor_sha256"]):
        raise ValueError("candidate export receipt does not bind checkpoint and descriptor")
    manifest_path = check(reservation["bundle_manifest_path"],
        reservation["bundle_manifest_sha256"], "bundle manifest")
    manifest = json.loads(manifest_path.read_text())
    validate_manifest_sources(manifest, reservation.get("source_sha256"))


def wait_for_consumed_reservation(path: Path, digest: str, timeout: float = 10.) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        owner = json.loads(path.read_text())
        if owner.get("reservation_sha256") != digest:
            raise ValueError("owner reservation changed after schedule launch")
        if owner.get("status") != "running":
            raise ValueError("owner campaign stopped before schedule started")
        if owner.get("seed_consumed") is True:
            return owner
        if time.monotonic() >= deadline:
            raise TimeoutError("owner did not seal setup seeds after successful schedule launch")
        time.sleep(0.05)


def wait_for_followup_reservation(path: Path, owner: dict, digest: str, timeout: float = 10.) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        followup = json.loads(path.read_text())
        registered = followup.get("opponent_search", {})
        if registered.get("reservation_sha256") not in (None, digest):
            raise ValueError("FOLLOWUP reservation changed after schedule launch")
        if (registered.get("status") == "running"
                and registered.get("reservation") == owner.get("reservation")
                and registered.get("reservation_sha256") == digest):
            return followup
        if time.monotonic() >= deadline:
            raise TimeoutError("FOLLOWUP did not activate the matching one-shot reservation")
        time.sleep(0.05)


def validate_shard_metadata(meta: dict, *, offset: int, paired_blocks: int,
                            iterations: int, master: int,
                            alpha_sims: int, preflight_run_sha256: str) -> None:
    diagnostic = meta.get("opponent_search_diagnostic", {})
    if (diagnostic.get("profile") != PROFILE
            or diagnostic.get("active_num_mcts_sims") != alpha_sims
            or diagnostic.get("setup_audit_sha256") != SETUP_AUDIT_SHA256
            or diagnostic.get("excluded_setup_ids_sha256") != EXCLUDED_SETUP_IDS_SHA256
            or diagnostic.get("preflight_run_json_sha256") != preflight_run_sha256
            or diagnostic.get("validated_master") != master
            or "reproduction_command" in diagnostic
            or not isinstance(meta.get("diagnostic_reproduction_command"), list)
            or meta.get("external_config", {}).get("numMCTSSims") != alpha_sims
            or meta.get("upstream_checkpoint_sha256") != sha(SOURCE / "splendor/pretrained_2players.pt")
            or diagnostic.get("checkpoint_sha256") != sha(SOURCE / "splendor/pretrained_2players.pt")
            or meta.get("iterations") != iterations or meta.get("master") != master
            or meta.get("offset_block") != offset or meta.get("games") != paired_blocks * 2):
        raise ValueError("shard settings differ from diagnostic plan")


def validate_shared_metadata(metas: list[dict]) -> None:
    if not metas:
        raise ValueError("no shard metadata to merge")
    common = ("model_sha256", "policy_binary_sha256", "strength_binary_sha256", "external_config",
        "upstream_revision", "upstream_checkpoint_sha256", "iterations", "depth", "world_pool",
        "chance_universes", "dynamic_fpu", "root_only", "search", "source_sha256",
        "opponent_search_diagnostic")
    for key in common:
        if any(meta.get(key) != metas[0].get(key) for meta in metas[1:]):
            raise ValueError(f"shards differ in {key}")


def owner_plan_fields(owner_path: Path, owner: dict) -> dict:
    """Return the reservation in the shape consumed by run_campaign."""
    return {"reservation": owner["reservation"],
        "owner_receipt": {"path": str(owner_path),
            "reservation_sha256": owner["reservation_sha256"],
            "reservation": owner["reservation"]}}


def run_schedule(args) -> dict:
    output = args.output.resolve()
    expected_seeds = fresh_master(args.master, args.games, output)
    owner_path = args.owner_receipt.resolve(strict=True)
    owner = json.loads(owner_path.read_text())
    if output.exists():
        raise ValueError("diagnostic output already exists")
    if args.games <= 0 or args.games % 2 or args.workers < 1 or args.workers > args.games // 2:
        raise ValueError("games must be even and workers must not exceed paired blocks")
    if args.alphazero_simulations not in (6400, 12800):
        raise ValueError("diagnostic AlphaZero simulations must be 6400 or 12800")

    policy = args.policy_binary.resolve(strict=True)
    strength = args.strength_binary.resolve(strict=True)
    model = args.model.resolve(strict=True) if args.model else None
    owner = wait_for_consumed_reservation(owner_path, args.owner_receipt_sha256)
    candidate_settings = {"algorithm": args.search, "iterations": args.iterations,
        "depth": args.depth, "world_pool": args.world_pool,
        "chance_universes": args.chance_universes, "dynamic_fpu": args.dynamic_fpu}
    validate_owner(owner, owner_path, args.owner_receipt_sha256, output,
        args.master, args.games, args.alphazero_simulations, candidate_settings,
        owner["reservation"]["candidate_checkpoint_sha256"], sha(model))
    validate_bundle(owner["reservation"], model, policy, strength)
    followup = wait_for_followup_reservation(ROOT / "research/sprint48/FOLLOWUP.json",
        owner, args.owner_receipt_sha256)
    registered = followup.get("opponent_search", {})
    if (registered.get("status") != "running"
            or registered.get("reservation") != owner["reservation"]
            or registered.get("reservation_sha256") != args.owner_receipt_sha256
            or owner["reservation"]["candidate_checkpoint_sha256"]
                != registered.get("candidate_checkpoint_sha256")):
        raise ValueError("FOLLOWUP does not contain the same active one-shot reservation")
    owner_sha = args.owner_receipt_sha256
    output.mkdir(parents=True)
    blocks = args.games // 2
    plans, offset = [], 0
    for worker in range(args.workers):
        count = blocks // args.workers + int(worker < blocks % args.workers)
        plans.append(build_command(args, offset, count * 2, output / f"shard-{worker:02}.jsonl"))
        offset += count

    schedule_hash = sha(Path(__file__))
    runner_hash = sha(RUNNER)
    plan = {"schema": "splendorust-az-search-diagnostic-plan-v1", "profile": PROFILE,
        "games": args.games, "master": args.master, "workers": args.workers,
        "candidate": {"search": args.search, "iterations": args.iterations,
            "depth": args.depth, "world_pool": args.world_pool,
            "chance_universes": args.chance_universes, "dynamic_fpu": args.dynamic_fpu,
            "root_only": args.root_only, "model_path": str(model),
            "model_sha256": sha(model) if model else None,
            "policy_binary_path": str(policy), "policy_binary_sha256": sha(policy),
            "strength_binary_path": str(strength), "strength_binary_sha256": sha(strength)},
        "opponent": {"name": "unchanged-pinned-AlphaZero-search-budget-diagnostic",
            "upstream_revision": PIN,
            "checkpoint_path": str(SOURCE / "splendor/pretrained_2players.pt"),
            "checkpoint_sha256": sha(SOURCE / "splendor/pretrained_2players.pt"),
            "checkpoint_num_mcts_sims": 800,
            "active_num_mcts_sims": args.alphazero_simulations,
        "setup_seed_audit_path": str(SETUP_AUDIT),
            "setup_seed_audit_sha256": SETUP_AUDIT_SHA256,
            "excluded_setup_ids_sha256": EXCLUDED_SETUP_IDS_SHA256,
            "preflight_run_json_sha256": json.loads(SETUP_AUDIT.read_text())["run_json_sha256"],
            "expected_setup_seed_sha256": hashlib.sha256(
                "".join(f"{seed}\n" for seed in expected_seeds).encode()).hexdigest()},
        # The campaign driver validates this exact immutable registration.
        **owner_plan_fields(owner_path, owner),
        "wrapper_sha256": {"schedule.py": schedule_hash, "run.py": runner_hash},
        "commands": plans}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    def execute(item):
        worker, command = item
        with (output / f"shard-{worker:02}.log").open("w") as log:
            start = time.perf_counter()
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
            return {"worker": worker, "exit": proc.returncode,
                "wall_seconds": time.perf_counter() - start}

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        executions = list(pool.map(execute, enumerate(plans)))
    wall = time.perf_counter() - start
    (output / "execution.json").write_text(json.dumps({"executions": executions,
        "wall_seconds": wall}, indent=2) + "\n")
    if any(row["exit"] != 0 for row in executions):
        raise RuntimeError("diagnostic shard failed; preserve output and investigate")

    metas, rows = [], []
    offset = 0
    for worker in range(args.workers):
        meta, *part = map(json.loads, (output / f"shard-{worker:02}.jsonl").read_text().splitlines())
        expected_count = blocks // args.workers + int(worker < blocks % args.workers)
        if len(part) != meta["games"]:
            raise ValueError(f"shard {worker} record count differs")
        validate_shard_metadata(meta, offset=offset, paired_blocks=expected_count,
            iterations=args.iterations, master=args.master,
            alpha_sims=args.alphazero_simulations,
            preflight_run_sha256=plan["opponent"]["preflight_run_json_sha256"])
        diagnostic = meta["opponent_search_diagnostic"]
        if diagnostic.get("owner_receipt_sha256") != owner_sha:
            raise ValueError(f"shard {worker} owner receipt differs from diagnostic plan")
        if meta.get("upstream_checkpoint_sha256") != plan["opponent"]["checkpoint_sha256"]:
            raise ValueError(f"shard {worker} checkpoint differs from diagnostic plan")
        metas.append(meta)
        rows.extend(part)
        offset += expected_count
    rows.sort(key=lambda row: row["index"])
    if len(rows) != args.games or [row["index"] for row in rows] != list(range(args.games)):
        raise ValueError("merged diagnostic rows are incomplete or unordered")
    validate_shared_metadata(metas)
    header = dict(metas[0], games=args.games, offset_block=0, workers=args.workers,
        wall_seconds=wall, wrapper_schedule_sha256=schedule_hash)
    with (output / "games.jsonl").open("x") as file:
        file.write(json.dumps(header) + "\n")
        for row in rows:
            file.write(json.dumps(row) + "\n")
    return {"profile": PROFILE, "games": len(rows), "master": args.master,
        "alphazero_simulations": args.alphazero_simulations, "wall_seconds": wall,
        "raw_path": str(output / "games.jsonl"), "plan_path": str(output / "plan.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, required=True)
    parser.add_argument("--master", type=int, required=True)
    parser.add_argument("--owner-receipt", type=Path, required=True)
    parser.add_argument("--owner-receipt-sha256", required=True)
    parser.add_argument("--alphazero-simulations", type=int, choices=(6400, 12800), required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=6400)
    parser.add_argument("--search", choices=("puct", "gumbel"), default="puct")
    parser.add_argument("--depth", type=int, default=64)
    parser.add_argument("--world-pool", type=int, default=3)
    parser.add_argument("--chance-universes", type=int, default=3)
    parser.add_argument("--gumbel-max-considered", type=int, default=16)
    parser.add_argument("--dynamic-fpu", action="store_true")
    parser.add_argument("--root-only", action="store_true")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--policy-binary", type=Path, default=ROOT / "target/release/examples/native_policy_worker")
    parser.add_argument("--strength-binary", type=Path, default=DEFAULT_STRENGTH_BINARY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run_schedule(args), sort_keys=True), flush=True)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
