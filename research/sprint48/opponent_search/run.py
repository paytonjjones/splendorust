#!/usr/bin/env python3
"""Run one native shard against a declared stronger AlphaZero search budget."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "benchmarks/strength/native"
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
import run as native_run

PROFILE = "alphazero-native-search-budget-diagnostic-v1"
ALPHAZERO_BASELINE_SIMS = 800
DIAGNOSTIC_SIM_COUNTS = (6400, 12800)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure_search(config, simulations: int) -> int:
    if simulations not in DIAGNOSTIC_SIM_COUNTS:
        raise ValueError(f"diagnostic AlphaZero simulations must be one of {DIAGNOSTIC_SIM_COUNTS}")
    baseline = getattr(config, "numMCTSSims", None)
    if baseline != ALPHAZERO_BASELINE_SIMS:
        raise ValueError(f"pinned checkpoint must declare {ALPHAZERO_BASELINE_SIMS} simulations")
    config.numMCTSSims = simulations
    return baseline


def assert_active_mcts_budget(config, tree, simulations: int) -> None:
    if tree.args is not config or tree.args.numMCTSSims != simulations:
        raise RuntimeError("diagnostic MCTS budget did not reach the active AlphaZero MCTS")


def reject_final_context(native_args: list[str]) -> None:
    if "--campaign-context" in native_args:
        raise ValueError("final campaign context cannot be used by this diagnostic profile")


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def service_config(reservation: dict) -> dict:
    service = reservation.get("service", {})
    return {key: service.get(key) for key in
        ("backend", "batch", "delay_ms", "port", "fast_entities", "slot")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alphazero-simulations", type=int, required=True)
    parser.add_argument("--owner-receipt", type=Path, required=True)
    parser.add_argument("--owner-receipt-sha256", required=True)
    args, native_args = parser.parse_known_args()
    try:
        reject_final_context(native_args)
    except ValueError as error:
        parser.error(str(error))
    try:
        if args.alphazero_simulations not in DIAGNOSTIC_SIM_COUNTS:
            raise ValueError(f"choose one of {DIAGNOSTIC_SIM_COUNTS}")
        if len(args.owner_receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.owner_receipt_sha256):
            raise ValueError("owner receipt SHA256 must be lowercase hexadecimal")
        owner = json.loads(args.owner_receipt.resolve(strict=True).read_text())
        reservation = owner.get("reservation")
        if (not isinstance(reservation, dict)
                or owner.get("reservation_sha256") != args.owner_receipt_sha256
                or canonical_digest(reservation) != args.owner_receipt_sha256
                or owner.get("schema") != "sprint48-opponent-search-campaign-v1"
                or owner.get("status") != "running" or owner.get("seed_consumed") is not True):
            raise ValueError("owner receipt is not a consumed active diagnostic reservation")
    except ValueError as error:
        parser.error(str(error))

    base_upstream = native_run.Upstream

    class DiagnosticUpstream(base_upstream):
        def __init__(self, *upstream_args, **upstream_kwargs):
            super().__init__(*upstream_args, **upstream_kwargs)
            self.pinned_num_mcts_sims = configure_search(self.config, args.alphazero_simulations)
            self.diagnostic_num_mcts_sims = args.alphazero_simulations

        def reset_policy(self, seed):
            super().reset_policy(seed)
            # MCTS holds this exact config object and reads numMCTSSims in
            # getActionProb. Fail if a future upstream wrapper copies or drops it.
            assert_active_mcts_budget(self.config, self.tree, self.diagnostic_num_mcts_sims)

    native_run.Upstream = DiagnosticUpstream
    apply_metadata = native_run.apply_campaign_metadata

    def add_diagnostic_metadata(metadata, run_args, model, policy_binary,
                                strength_binary, external_config):
        if run_args.campaign_context is not None:
            raise ValueError("final campaign context cannot be used by this diagnostic profile")
        result = apply_metadata(metadata, run_args, model, policy_binary,
                                strength_binary, external_config)
        files = {
            "research/sprint48/opponent_search/run.py": Path(__file__).resolve(),
            "research/sprint48/opponent_search/schedule.py": Path(__file__).with_name("schedule.py").resolve(),
        }
        result["source_sha256"].update({name: sha(path) for name, path in files.items()})
        seed_audit_path = ROOT / "local/research/sprint48/opponent-search-preflight/setup-audit.json"
        excluded_ids_path = ROOT / "local/research/sprint48/opponent-search-preflight/excluded-setup-ids.txt"
        seed_audit = json.loads(seed_audit_path.read_text())
        reservation = owner["reservation"]
        candidate_search = {"algorithm": run_args.search, "iterations": run_args.iterations,
            "depth": run_args.depth, "world_pool": run_args.world_pool,
            "chance_universes": run_args.chance_universes, "dynamic_fpu": run_args.dynamic_fpu}
        binaries = reservation.get("candidate_artifacts", {}).get("binaries", {})
        if (reservation.get("master") != run_args.master
                or reservation.get("games") < run_args.offset_block * 2 + run_args.games
                or reservation.get("opponent_simulations") != args.alphazero_simulations
                or reservation.get("candidate_search") != candidate_search
                or reservation.get("schedule_output") != str(run_args.output.resolve().parent)
                or reservation.get("candidate_descriptor_path") != str(model.resolve())
                or reservation.get("candidate_descriptor_sha256") != sha(model)
                or binaries.get("native_policy_worker", {}).get("sha256") != sha(policy_binary)
                or binaries.get("strength_worker", {}).get("sha256") != sha(strength_binary)
                or service_config(reservation) != {"backend": "mps", "batch": 32,
                    "delay_ms": 1, "port": 19760, "fast_entities": True, "slot": 13}):
            raise ValueError("native shard settings differ from the one-shot owner reservation")
        if (sha(seed_audit_path) != "a92ca6b397c9cffd6d0a24f9a7984377254fc5d0e0055076beffdbbdbbf91b0a"
                or sha(excluded_ids_path) != "6f5e7a9f13efde03bd589692f89a04af134ef5944a5e213f90f2bc51044a8a13"
                or run_args.master != seed_audit.get("proposed_master")
                or run_args.offset_block + run_args.games // 2 > seed_audit.get("paired_blocks", 0)):
            raise ValueError("shard differs from the hash-bound setup-seed preflight")
        result["opponent_search_diagnostic"] = {
            "profile": PROFILE,
            "checkpoint_num_mcts_sims": ALPHAZERO_BASELINE_SIMS,
            "active_num_mcts_sims": args.alphazero_simulations,
            "checkpoint_sha256": sha(native_run.SOURCE / "splendor/pretrained_2players.pt"),
            "upstream_revision": native_run.PIN,
            "wrapper_sha256": result["source_sha256"]["research/sprint48/opponent_search/run.py"],
            "setup_audit_sha256": sha(seed_audit_path),
            "excluded_setup_ids_sha256": sha(excluded_ids_path),
            "preflight_run_json_sha256": seed_audit["run_json_sha256"],
            "preflight_games": seed_audit["games"],
            "validated_master": run_args.master,
            "owner_receipt_sha256": args.owner_receipt_sha256,
            "owner_receipt_path": str(args.owner_receipt.resolve()),
            "reservation": owner["reservation"],
        }
        # Shard paths, offsets, and game counts differ by worker. Keep this
        # command outside the invariant diagnostic profile object.
        result["diagnostic_reproduction_command"] = [sys.executable, str(Path(__file__).resolve()),
                "--alphazero-simulations", str(args.alphazero_simulations),
                "--owner-receipt", str(args.owner_receipt.resolve()),
                "--owner-receipt-sha256", args.owner_receipt_sha256, *native_args]
        return result

    native_run.apply_campaign_metadata = add_diagnostic_metadata
    sys.argv = [str(Path(__file__).resolve()), *native_args]
    native_run.main()


if __name__ == "__main__":
    main()
