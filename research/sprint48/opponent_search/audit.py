#!/usr/bin/env python3
"""Replay and summarize one completed stronger-AlphaZero diagnostic schedule."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "benchmarks/strength/native"
PROFILE = "alphazero-native-search-budget-diagnostic-v1"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
_SCHEDULE_SPEC = importlib.util.spec_from_file_location(
    "opponent_search_diagnostic_schedule_audit", Path(__file__).with_name("schedule.py"))
_SCHEDULE = importlib.util.module_from_spec(_SCHEDULE_SPEC)
_SCHEDULE_SPEC.loader.exec_module(_SCHEDULE)


def validate_header(metadata: dict, plan: dict) -> None:
    opponent = plan["opponent"]
    candidate = plan["candidate"]
    diag = metadata.get("opponent_search_diagnostic", {})
    if (plan.get("profile") != PROFILE or metadata.get("games") != plan.get("games")
            or metadata.get("master") != plan.get("master")
            or metadata.get("upstream_revision") != opponent.get("upstream_revision")
            or metadata.get("upstream_checkpoint_sha256") != opponent.get("checkpoint_sha256")
            or metadata.get("external_config", {}).get("numMCTSSims") != opponent.get("active_num_mcts_sims")
            or diag.get("profile") != PROFILE
            or diag.get("checkpoint_num_mcts_sims") != 800
            or diag.get("active_num_mcts_sims") != opponent.get("active_num_mcts_sims")
            or diag.get("checkpoint_sha256") != opponent.get("checkpoint_sha256")
            or metadata.get("iterations") != candidate.get("iterations")
            or metadata.get("search") != candidate.get("search")
            or metadata.get("depth") != candidate.get("depth")
            or metadata.get("world_pool") != candidate.get("world_pool")
            or metadata.get("chance_universes") != candidate.get("chance_universes")
            or metadata.get("dynamic_fpu") != candidate.get("dynamic_fpu")
            or metadata.get("root_only") != candidate.get("root_only")
            or metadata.get("model_sha256") != candidate.get("model_sha256")
            or metadata.get("policy_binary_sha256") != candidate.get("policy_binary_sha256")
            or metadata.get("strength_binary_sha256") != candidate.get("strength_binary_sha256")):
        raise ValueError("raw header differs from the diagnostic plan or does not use its declared stronger opponent search")
    if metadata.get("wrapper_schedule_sha256") != plan.get("wrapper_sha256", {}).get("schedule.py"):
        raise ValueError("raw schedule wrapper hash differs from its plan")
    wrapper_hashes = plan.get("wrapper_sha256", {})
    for name, digest in wrapper_hashes.items():
        path = ROOT / "research/sprint48/opponent_search" / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"diagnostic wrapper changed since scheduling: {name}")
    owner_binding = plan.get("owner_receipt", {})
    owner_path = Path(owner_binding.get("path", ""))
    owner = json.loads(owner_path.read_text())
    reservation = owner.get("reservation")
    if (owner.get("schema") != "sprint48-opponent-search-campaign-v1"
            or owner.get("status") != "complete" or owner.get("seed_consumed") is not True
            or not isinstance(reservation, dict)):
        raise ValueError("owner receipt has no immutable diagnostic reservation")
    reservation_hash = hashlib.sha256(json.dumps(reservation, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    if (reservation_hash != owner_binding.get("reservation_sha256")
            or owner.get("reservation_sha256") != reservation_hash
            or reservation != owner_binding.get("reservation")
            or reservation != diag.get("reservation")
            or diag.get("owner_receipt_sha256") != reservation_hash
            or reservation.get("master") != plan.get("master")
            or reservation.get("games") != plan.get("games")
            or reservation.get("opponent_simulations") != opponent.get("active_num_mcts_sims")
            or reservation.get("candidate_search") != {"algorithm": candidate.get("search"),
                "iterations": candidate.get("iterations"), "depth": candidate.get("depth"),
                "world_pool": candidate.get("world_pool"),
                "chance_universes": candidate.get("chance_universes"),
                "dynamic_fpu": candidate.get("dynamic_fpu")}
            or reservation.get("candidate_descriptor_sha256") != candidate.get("model_sha256")):
        raise ValueError("owner reservation does not bind the diagnostic plan and raw metadata")
    service = reservation.get("service", {})
    if any(service.get(key) != value for key, value in {
            "backend": "mps", "batch": 32, "delay_ms": 1,
            "port": 19760, "fast_entities": True, "slot": 13}.items()):
        raise ValueError("owner reservation inference-service configuration differs from the diagnostic profile")
    for relative, digest in metadata.get("source_sha256", {}).items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"native source changed since diagnostic run: {relative}")
    for sha_key, path_key in (("model_sha256", "model_path"),
            ("policy_binary_sha256", "policy_binary_path"),
            ("strength_binary_sha256", "strength_binary_path")):
        path = Path(metadata.get(path_key, ""))
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get(sha_key):
            raise ValueError(f"diagnostic artifact hash differs: {path_key}")


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"audit command failed: {' '.join(command)}\n{result.stderr}")


def audit(raw_path: Path, plan_path: Path, output_dir: Path) -> dict:
    raw_path = raw_path.resolve(strict=True)
    plan_path = plan_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError("audit output directory already exists")
    plan = json.loads(plan_path.read_text())
    raw = raw_path.read_bytes()
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not records:
        raise ValueError("diagnostic raw file is empty")
    metadata, rows = records[0], records[1:]
    validate_header(metadata, plan)
    _SCHEDULE.validate_bundle(metadata["opponent_search_diagnostic"]["reservation"],
        Path(metadata["model_path"]), Path(metadata["policy_binary_path"]),
        Path(metadata["strength_binary_path"]))
    owner = json.loads(Path(plan["owner_receipt"]["path"]).read_text())
    if owner["reservation"].get("schedule_output") != str(raw_path.parent):
        raise ValueError("owner receipt output path differs from the raw file directory")
    if len(rows) != plan["games"]:
        raise ValueError("diagnostic raw file does not contain the complete fixed game count")

    output_dir.mkdir(parents=True)
    replay_path, evidence_path, summary_path = (output_dir / name for name in
        ("replay.json", "evidence.json", "summary.json"))
    run([sys.executable, str(NATIVE / "replay.py"), str(raw_path), "--output", str(replay_path)])
    run([sys.executable, str(ROOT / "research/sprint48/evidence.py"), str(raw_path), "--output", str(evidence_path)])
    run([sys.executable, str(NATIVE / "summarize.py"), str(raw_path), "--output", str(summary_path)])
    replay = json.loads(replay_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    summary = json.loads(summary_path.read_text())
    raw_hash = hashlib.sha256(raw).hexdigest()
    if (replay.get("checked_games") != plan["games"] or replay.get("raw_sha256") != raw_hash
            or evidence.get("games") != plan["games"] or evidence.get("raw_sha256") != raw_hash
            or summary.get("games") != plan["games"] or summary.get("raw_sha256") != raw_hash):
        raise ValueError("replay or regenerated statistics do not bind the complete raw file")
    report = {"schema": "splendorust-az-search-diagnostic-audit-v1",
        "status": "complete", "profile": PROFILE, "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "raw_sha256": raw_hash, "games": evidence["games"], "setup_blocks": evidence["setup_blocks"],
        "opponent_search_simulations": metadata["external_config"]["numMCTSSims"],
        "candidate_iterations": metadata["iterations"], "statuses": evidence["statuses"],
        "evidence_rejections": evidence["evidence_rejections"],
        "no_action_fraction": evidence["statuses"].get("no_legal_action", 0) / evidence["games"],
        "terminal_categories": evidence["terminal_categories"],
        "all_requested_credit_bounds": evidence["all_requested_credit_bounds"],
        "primary_hoeffding95": evidence["conservative_hoeffding95_missing_envelope"],
        "caps_as_unknown_credit_bounds": evidence["caps_as_unknown_credit_bounds"],
        "caps_as_unknown_hoeffding95": evidence["caps_as_unknown_hoeffding95"],
        "native_turn_cap_count": evidence["terminal_categories"].get("native_turn_cap", 0),
        "claim_supported": evidence["decisive_native_criterion"],
        "claim_supported_with_caps_unknown": evidence["decisive_with_caps_unknown"],
        "replay_checked_transitions": replay["checked_transitions"],
        "simulations": summary["simulations"], "inferences": summary["inferences"],
        "wall_seconds": summary["wall_seconds"],
        "evidence_path": str(evidence_path), "summary_path": str(summary_path),
        "replay_path": str(replay_path),
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.raw, args.plan, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
