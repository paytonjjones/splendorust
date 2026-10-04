"""CPU-only tests for the guarded pre-freeze reservation repair."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/sprint48"))
import repair_final_preparation as repair


class RepairFinalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48")
        self.base = Path(self.temp.name)
        self.run_path = self.base / "RUN.json"
        self.output = self.base / "final-native"
        self.retry = self.base / "final-native-retry"
        self.checkpoint = self.base / "candidate.pt"
        self.checkpoint.write_bytes(b"registered candidate bytes")
        self.campaign_id = "a" * 32
        selection = {
            "backend": "mps", "batch": 32, "chance_universes": 3,
            "checkpoint": str(self.checkpoint),
            "checkpoint_sha256": repair._sha_file(self.checkpoint),
            "depth": 64, "dynamic_fpu": True, "games": 1000,
            "iterations": 6400, "search": "puct", "workers": 64,
            "world_pool": 3,
        }
        campaign = {
            "schema": "sprint48-final-campaign-v1", "id": self.campaign_id,
            "status": "failed", "output": str(self.output), "master": 17_790_000_000,
            "games": 1000, "search": "puct", "iterations": 6400, "depth": 64,
            "world_pool": 3, "chance_universes": 3, "dynamic_fpu": True,
            "gumbel_max_considered": None, "root_only": False,
            "workers": 64, "backend": "mps", "batch": 32,
            "checkpoint_sha256": selection["checkpoint_sha256"],
            "driver_pid": 910001, "service_pid": 910002,
            "error": 'FreezeError("cannot read repo: [Errno 21] Is a directory")',
            "finished_at_utc": "2026-10-04T03:31:05Z",
        }
        self.run = {"status": "active", "final_seed_sealed": True,
                    "final_selection": selection, "final_campaign": campaign,
                    "consumed_trials": [], "failed_attempts": []}
        self.run_path.write_text(json.dumps(self.run))
        self.output.mkdir()
        (self.output / "input").mkdir()
        (self.output / "input/candidate.pt").write_bytes(self.checkpoint.read_bytes())
        (self.output / "sources").mkdir()
        (self.output / "sources/source.py").write_text("frozen source\n")
        (self.output / "service").mkdir()
        (self.output / "service/run.json").write_text(json.dumps({"pid": 910002}))
        (self.output / "parity-command").mkdir()
        (self.output / "parity-command/process.json").write_text(json.dumps({"pid": 910003}))
        (self.output / "parity-command/exit.json").write_text(json.dumps({"returncode": 0}))
        private = {**{key: campaign[key] for key in (
            "backend", "batch", "chance_universes", "depth", "dynamic_fpu", "games",
            "iterations", "master", "search", "workers", "world_pool",
            "gumbel_max_considered", "root_only")},
            "schema": "sprint48-final-run-v1", "status": "failed",
            "campaign_id": self.campaign_id, "output": str(self.output),
            "checkpoint_source": str(self.checkpoint),
            "checkpoint_source_sha256": repair._sha_file(self.checkpoint),
            "error": campaign["error"]}
        (self.output / "run.json").write_text(json.dumps(private))
        self.failed_output_patch = mock.patch.object(repair, "FAILED_OUTPUT", self.output)
        self.failed_output_patch.start()
        self.pid_patch = mock.patch.object(repair, "pid_is_alive", return_value=False)
        self.pid_patch.start()

    def tearDown(self):
        self.pid_patch.stop()
        self.failed_output_patch.stop()
        self.temp.cleanup()

    def test_dry_run_records_hashes_without_changing_run(self):
        before = self.run_path.read_bytes()
        record = repair.repair(self.run_path, self.campaign_id, self.retry, apply=False)
        self.assertFalse(record["repair_applied"])
        self.assertEqual(self.run_path.read_bytes(), before)
        self.assertIn("sources/source.py", record["source_sha256"])
        self.assertIn("run.json", record["retained_output_files"])
        self.assertEqual(record["processes_confirmed_dead"],
                         {"driver": 910001, "service": 910002, "parity": 910003})

    def test_apply_keeps_seed_sealed_and_preserves_failed_campaign_record(self):
        record = repair.repair(self.run_path, self.campaign_id, self.retry, apply=True)
        updated = json.loads(self.run_path.read_text())
        self.assertIsNone(updated["final_campaign"])
        self.assertIs(updated["final_seed_sealed"], True)
        self.assertEqual(updated["failed_attempts"][-1]["campaign_record"]["id"], self.campaign_id)
        self.assertEqual(updated["failed_attempts"][-1]["retained_output_tree_sha256"],
                         record["retained_output_tree_sha256"])
        self.assertTrue(updated["failed_attempts"][-1]["repair_applied"])
        self.assertTrue(self.output.exists())
        self.assertNotIn("repair_final_preparation", updated)

    def test_rejects_seeded_frozen_or_game_evidence(self):
        campaign = self.run["final_campaign"]
        campaign["schedule_pid"] = 123
        self.run_path.write_text(json.dumps(self.run))
        with self.assertRaisesRegex(ValueError, "advanced past preparation"):
            repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)
        del campaign["schedule_pid"]
        self.run_path.write_text(json.dumps(self.run))

        private_path = self.output / "run.json"
        private = json.loads(private_path.read_text())
        private["freeze_sha256"] = "deadbeef"
        private_path.write_text(json.dumps(private))
        with self.assertRaisesRegex(ValueError, "schedule, freeze, or seed"):
            repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)
        del private["freeze_sha256"]
        private_path.write_text(json.dumps(private))

        (self.output / "final-freeze.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "freeze file"):
            repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)
        (self.output / "final-freeze.json").unlink()
        (self.output / "arena-command").mkdir()
        with self.assertRaisesRegex(ValueError, "game or schedule"):
            repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)

    def test_rejects_alive_process_and_selection_or_output_mismatch(self):
        with mock.patch.object(repair, "pid_is_alive", side_effect=lambda pid: pid == 910001):
            with self.assertRaisesRegex(ValueError, "driver process is still alive"):
                repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)
        changed = json.loads(self.run_path.read_text())
        changed["final_selection"]["iterations"] = 800
        self.run_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "selection mismatch"):
            repair.inspect_attempt(self.run_path, self.campaign_id, self.retry)


if __name__ == "__main__":
    unittest.main()
