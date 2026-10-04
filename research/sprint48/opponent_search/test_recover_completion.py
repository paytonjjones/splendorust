from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "opponent_search_recover_completion", Path(__file__).with_name("recover_completion.py"))
recover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recover)


class CompletionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config_800 = {"numMCTSSims": 800, "fpu": 0.0593,
            "universes": 3, "cpuct": 0.8, "prob_fullMCTS": 1.0,
            "forced_playouts": False, "no_mem_optim": False}
        self.plan = {"opponent": {"checkpoint_sha256": "checkpoint",
            "upstream_revision": "pinned"}}
        self.reservation = {"master": 17792000000, "games": 1000}
        self.header = {"external_config": dict(self.config_800),
            "upstream_checkpoint_sha256": "checkpoint", "upstream_revision": "pinned",
            "opponent_search_diagnostic": {"checkpoint_num_mcts_sims": 800,
                "active_num_mcts_sims": 6400, "checkpoint_sha256": "checkpoint",
                "upstream_revision": "pinned", "owner_receipt_sha256": "reservation-sha",
                "reservation": self.reservation}}

    def test_accepts_800_checkpoint_dict_with_6400_active_diagnostic(self):
        recover.validate_opponent_config(self.header, self.config_800, self.plan,
            "reservation-sha", self.reservation)

    def test_rejects_active_budget_or_checkpoint_dict_mismatch(self):
        bad_active = {**self.header, "opponent_search_diagnostic": {
            **self.header["opponent_search_diagnostic"], "active_num_mcts_sims": 800}}
        with self.assertRaisesRegex(ValueError, "unchanged 800"):
            recover.validate_opponent_config(bad_active, self.config_800, self.plan,
                "reservation-sha", self.reservation)
        bad_config = {**self.header, "external_config": {**self.config_800, "numMCTSSims": 6400}}
        with self.assertRaisesRegex(ValueError, "unchanged 800"):
            recover.validate_opponent_config(bad_config, self.config_800, self.plan,
                "reservation-sha", self.reservation)

    def test_rejects_reservation_mismatch(self):
        with self.assertRaisesRegex(ValueError, "unchanged 800"):
            recover.validate_opponent_config(self.header, self.config_800, self.plan,
                "wrong-digest", self.reservation)

    def test_rejects_unbound_header_source_hash(self):
        reservation = {"source_sha256": {"src/a.py": "a"}}
        recover.validate_header_sources({"source_sha256": {"src/a.py": "a"}}, reservation)
        with self.assertRaisesRegex(ValueError, "src/a.py"):
            recover.validate_header_sources({"source_sha256": {"src/a.py": "wrong"}}, reservation)

    def test_rejects_candidate_path_or_binary_hash_drift(self):
        reservation = {"candidate_descriptor_path": "/bundle/model.bin",
            "candidate_descriptor_sha256": "model-hash",
            "candidate_artifacts": {"binaries": {
                "native_policy_worker": {"path": "/bundle/policy", "sha256": "policy-hash"},
                "strength_worker": {"path": "/bundle/strength", "sha256": "strength-hash"}}}}
        plan = {"candidate": {"model_path": "/bundle/model.bin", "model_sha256": "model-hash",
            "policy_binary_path": "/bundle/policy", "policy_binary_sha256": "policy-hash",
            "strength_binary_path": "/bundle/strength", "strength_binary_sha256": "strength-hash"}}
        recover.validate_candidate_artifacts(plan, reservation)
        plan["candidate"]["policy_binary_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "policy binary"):
            recover.validate_candidate_artifacts(plan, reservation)

    def test_plan_search_and_opponent_must_match_owner(self):
        reservation = {"candidate_search": {"algorithm": "puct", "iterations": 6400,
            "depth": 64, "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True}}
        plan = {"candidate": {"search": "puct", "iterations": 6400, "depth": 64,
            "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True, "root_only": False},
            "opponent": {"upstream_revision": "pin", "checkpoint_sha256": "sha"}}
        receipt = {"pinned_upstream": {"revision": "pin", "checkpoint_sha256": "sha"}}
        recover.validate_plan_profile(plan, reservation, receipt)
        plan["candidate"]["iterations"] = 800
        with self.assertRaisesRegex(ValueError, "candidate search"):
            recover.validate_plan_profile(plan, reservation, receipt)
        plan["candidate"]["iterations"] = 6400
        receipt["pinned_upstream"]["revision"] = "other"
        with self.assertRaisesRegex(ValueError, "pinned owner receipt"):
            recover.validate_plan_profile(plan, reservation, receipt)

    def test_fixed_shard_fanout(self):
        counts = recover.expected_shard_counts()
        self.assertEqual(len(counts), 64)
        self.assertEqual(counts[0], (0, 8))
        self.assertEqual(counts[51], (408, 8))
        self.assertEqual(counts[52], (416, 7))
        self.assertEqual(counts[-1], (493, 7))
        self.assertEqual(sum(blocks for _, blocks in counts) * 2, 1000)

    def test_loads_isolated_diagnostic_scheduler(self):
        module = recover.load_diagnostic_schedule()
        self.assertEqual(Path(module.__file__).resolve(), recover.DIAGNOSTIC_SCHEDULE)
        self.assertTrue(callable(module.validate_setup_seeds))

    def test_wait_mode_waits_for_running_to_become_failed_then_stopped(self):
        states = iter(({"status": "running", "deadline_unix": 100},
                       {"status": "failed", "deadline_unix": 100}))
        stopped = []
        sleeps = []
        def check(_path, receipt):
            stopped.append(receipt["status"])
        result = recover.wait_until_stopped(Path("/tmp/campaign"),
            load_receipt=lambda _path: next(states), stopped_check=check,
            sleep=sleeps.append, now=lambda: 1)
        self.assertEqual(sleeps, [10])
        self.assertEqual(stopped, ["failed"])
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
