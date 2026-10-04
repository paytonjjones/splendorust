"""Bounded tests for the completed-campaign auditor; no final rows are read."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/sprint48"))
import audit_final
import freeze


class FinalAuditTests(unittest.TestCase):
    def test_partial_campaign_is_rejected_before_audit(self):
        output = ROOT / "local/research/sprint48/not-a-real-final-output"
        run = {"schema": "splendorust-strength-sprint-run-v1", "final_campaign": {
            "status": "running", "output": str(output), "id": "campaign"}}
        private = {"schema": "sprint48-final-run-v1", "status": "running",
            "output": str(output), "campaign_id": "campaign", "master": freeze.MASTER, "games": 1000}
        with self.assertRaisesRegex(ValueError, "waits for RUN and private campaign status complete"):
            audit_final.require_complete(run, private, output)

    def test_raw_validation_checks_all_fixed_pairs_and_unique_setup_ids(self):
        metadata = {"games": 4, "campaign_games": 4, "master": freeze.MASTER, "offset_block": 0}
        rows = []
        for block in range(2):
            seed = audit_final.setup_seed(freeze.MASTER, block)
            for rotation in range(2):
                rows.append({"index": 2 * block + rotation, "block": block,
                    "rotation": rotation, "setup_seed": seed,
                    "seats": ["champion", "alphazero"] if rotation == 0 else ["alphazero", "champion"],
                    "initial_state": [block, 0]})
        with tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48") as directory:
            path = Path(directory) / "games.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in [metadata, *rows]) + "\n")
            checked, _ = audit_final.validate_raw(path, metadata, games=4)
            self.assertEqual(len(checked), 4)
            rows[3]["setup_seed"] = rows[1]["setup_seed"]
            path.write_text("\n".join(json.dumps(row) for row in [metadata, *rows]) + "\n")
            with self.assertRaisesRegex(ValueError, "setup seed differs or repeats"):
                audit_final.validate_raw(path, metadata, games=4)

    def test_regenerated_metrics_must_match_saved_metrics(self):
        original = {"games": 1000, "caps_as_unknown_hoeffding95": [0.1, 0.8]}
        audit_final.compare_metrics(original, dict(original), tuple(original), "evidence")
        changed = dict(original, games=998)
        with self.assertRaisesRegex(ValueError, "metric differs after regeneration: games"):
            audit_final.compare_metrics(original, changed, tuple(original), "evidence")


if __name__ == "__main__":
    unittest.main()
