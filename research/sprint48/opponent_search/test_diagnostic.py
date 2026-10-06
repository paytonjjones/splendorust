from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research/sprint48/opponent_search"))
import run
import audit
SCHEDULE_SPEC = importlib.util.spec_from_file_location(
    "opponent_search_diagnostic_schedule", Path(__file__).with_name("schedule.py"))
schedule = importlib.util.module_from_spec(SCHEDULE_SPEC)
SCHEDULE_SPEC.loader.exec_module(schedule)


class DiagnosticBudgetTests(unittest.TestCase):
    def test_config_object_gets_override_in_place(self):
        config = SimpleNamespace(numMCTSSims=800)
        identity = id(config)
        baseline = run.configure_search(config, 6400)
        self.assertEqual(baseline, 800)
        self.assertEqual(config.numMCTSSims, 6400)
        self.assertEqual(id(config), identity)

    def test_rejects_nonpinned_baseline_and_unregistered_budget(self):
        with self.assertRaisesRegex(ValueError, "must declare 800"):
            run.configure_search(SimpleNamespace(numMCTSSims=1600), 6400)
        with self.assertRaisesRegex(ValueError, "one of"):
            run.configure_search(SimpleNamespace(numMCTSSims=800), 3200)

    def test_active_mcts_uses_same_mutated_config_object(self):
        config = SimpleNamespace(numMCTSSims=6400)
        run.assert_active_mcts_budget(config, SimpleNamespace(args=config), 6400)
        with self.assertRaisesRegex(RuntimeError, "did not reach"):
            run.assert_active_mcts_budget(config, SimpleNamespace(args=SimpleNamespace(numMCTSSims=6400)), 6400)

    def test_setup_seed_preflight_rejects_changed_master(self):
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            schedule.validate_setup_seeds(17792000001, 2)

    def test_owner_receipt_binds_one_output_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native"
            reservation = {"profile": schedule.PROFILE, "master": 17792000000,
                "games": 1000, "schedule_output": str(output), "opponent_simulations": 6400,
                "candidate_search": {"algorithm": "puct", "iterations": 6400,
                    "depth": 64, "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True},
                "candidate_checkpoint_sha256": "checkpoint",
                "candidate_descriptor_sha256": "descriptor"}
            digest = schedule.canonical_digest(reservation)
            owner = {"schema": "sprint48-opponent-search-campaign-v1", "status": "running",
                "reservation": reservation, "reservation_sha256": digest}
            schedule.validate_owner(owner, Path(directory) / "run.json", digest, output,
                17792000000, 1000, 6400, reservation["candidate_search"], "checkpoint", "descriptor")
            with self.assertRaisesRegex(ValueError, "does not reserve"):
                schedule.validate_owner(owner, Path(directory) / "run.json", digest, output,
                    17792000000, 1000, 12800, reservation["candidate_search"], "checkpoint", "descriptor")

    def test_schedule_plan_exposes_exact_top_level_reservation(self):
        reservation = {"profile": schedule.PROFILE, "master": 17792000000,
            "games": 1000, "schedule_output": "/tmp/diagnostic",
            "candidate_checkpoint_sha256": "checkpoint"}
        owner = {"reservation": reservation, "reservation_sha256": "digest"}
        fields = schedule.owner_plan_fields(Path("/tmp/run.json"), owner)
        self.assertEqual(fields["reservation"], reservation)
        self.assertEqual(fields["owner_receipt"]["reservation"], reservation)
        self.assertEqual(fields["owner_receipt"]["reservation_sha256"], "digest")

    def test_two_shards_keep_diagnostic_metadata_shared(self):
        checkpoint_hash = schedule.sha(schedule.SOURCE / "splendor/pretrained_2players.pt")
        diagnostic = {"profile": schedule.PROFILE, "active_num_mcts_sims": 6400,
            "setup_audit_sha256": schedule.SETUP_AUDIT_SHA256,
            "excluded_setup_ids_sha256": schedule.EXCLUDED_SETUP_IDS_SHA256,
            "preflight_run_json_sha256": "preflight", "validated_master": 17792000000,
            "checkpoint_sha256": checkpoint_hash, "reservation": {"fixed": True}}
        common = {"model_sha256": "model", "policy_binary_sha256": "policy",
            "strength_binary_sha256": "strength", "external_config": {"numMCTSSims": 6400},
            "upstream_revision": "pin", "upstream_checkpoint_sha256": checkpoint_hash,
            "iterations": 6400, "depth": 64, "world_pool": 3, "chance_universes": 3,
            "dynamic_fpu": True, "root_only": False, "search": "puct",
            "source_sha256": {"source.py": "hash"}, "opponent_search_diagnostic": diagnostic}
        shard_a = {**common, "master": 17792000000, "offset_block": 0, "games": 16,
            "diagnostic_reproduction_command": ["run.py", "--offset-block", "0",
                "--games", "16", "--output", "shard-00.jsonl"]}
        shard_b = {**common, "master": 17792000000, "offset_block": 8, "games": 16,
            "diagnostic_reproduction_command": ["run.py", "--offset-block", "8",
                "--games", "16", "--output", "shard-01.jsonl"]}
        schedule.validate_shared_metadata([shard_a, shard_b])
        for shard, offset in ((shard_a, 0), (shard_b, 8)):
            schedule.validate_shard_metadata(shard, offset=offset, paired_blocks=8,
                iterations=6400, master=17792000000, alpha_sims=6400,
                preflight_run_sha256="preflight")
        self.assertNotEqual(shard_a["diagnostic_reproduction_command"],
            shard_b["diagnostic_reproduction_command"])
        self.assertNotIn("reproduction_command", diagnostic)

    def test_bundle_manifest_binds_copy_of_each_source(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "copy.py"
            copied.write_text("frozen")
            digest = run.sha(copied)
            schedule.validate_manifest_sources({"source_sha256": {"example/source.py": digest},
                "files": {"sources": {"campaign-source:example/source.py": {
                    "path": str(copied), "sha256": digest}}}}, {"example/source.py": digest})
            copied.write_text("changed")
            with self.assertRaisesRegex(ValueError, "copied source hash differs"):
                schedule.validate_manifest_sources({"source_sha256": {"example/source.py": digest},
                    "files": {"sources": {"campaign-source:example/source.py": {
                        "path": str(copied), "sha256": digest}}}}, {"example/source.py": digest})

    def test_final_context_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "final campaign context"):
            run.reject_final_context(["--games", "2", "--campaign-context", "freeze.json"])

    def test_audit_binds_diagnostic_budget_and_rejects_800_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_paths = {name: Path(directory) / name for name in ("model", "policy", "strength")}
            for path in artifact_paths.values():
                path.write_text(path.name)
            artifact_hashes = {name: run.sha(path) for name, path in artifact_paths.items()}
            candidate = {"iterations": 6400, "search": "puct", "depth": 64,
                "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True,
                "root_only": False, "model_sha256": artifact_hashes["model"],
                "policy_binary_sha256": artifact_hashes["policy"],
                "strength_binary_sha256": artifact_hashes["strength"]}
            reservation = {"master": 17792000000, "games": 1000,
                "opponent_simulations": 6400,
                "candidate_search": {"algorithm": "puct", "iterations": 6400,
                    "depth": 64, "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True},
                "candidate_descriptor_sha256": artifact_hashes["model"],
                "service": {"backend": "mps", "batch": 32, "delay_ms": 1,
                    "port": 19760, "fast_entities": True, "slot": 13}}
            digest = schedule.canonical_digest(reservation)
            owner_path = Path(directory) / "run.json"
            owner_path.write_text(json.dumps({"schema": "sprint48-opponent-search-campaign-v1",
                "status": "complete", "seed_consumed": True, "reservation": reservation,
                "reservation_sha256": digest}))
            plan = {"profile": audit.PROFILE, "master": 17792000000, "games": 1000,
                "opponent": {"upstream_revision": "pin", "checkpoint_sha256": "checkpoint",
                    "active_num_mcts_sims": 6400}, "candidate": candidate,
                "wrapper_sha256": {}, "owner_receipt": {"path": str(owner_path),
                "reservation_sha256": digest, "reservation": reservation}}
            header = {"games": 1000, "master": 17792000000, "upstream_revision": "pin",
                "upstream_checkpoint_sha256": "checkpoint", "external_config": {"numMCTSSims": 6400},
                "opponent_search_diagnostic": {"profile": audit.PROFILE,
                    "checkpoint_num_mcts_sims": 800, "active_num_mcts_sims": 6400,
                    "checkpoint_sha256": "checkpoint", "owner_receipt_sha256": digest,
                    "reservation": reservation},
                "iterations": 6400, "search": "puct", "depth": 64, "world_pool": 3,
                "chance_universes": 3, "dynamic_fpu": True, "root_only": False,
                "model_sha256": artifact_hashes["model"], "model_path": str(artifact_paths["model"]),
                "policy_binary_sha256": artifact_hashes["policy"],
                "policy_binary_path": str(artifact_paths["policy"]),
                "strength_binary_sha256": artifact_hashes["strength"],
                "strength_binary_path": str(artifact_paths["strength"])}
            audit.validate_header(header, plan)
            header["external_config"]["numMCTSSims"] = 800
            with self.assertRaisesRegex(ValueError, "stronger opponent search"):
                audit.validate_header(header, plan)


if __name__ == "__main__":
    unittest.main()
