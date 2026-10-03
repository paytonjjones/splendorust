"""Read-only branch-two wrapper preflight checks."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.sprint48 import run_branch2


class CampaignPreflightTests(unittest.TestCase):
    def test_dry_run_can_validate_during_active_external_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_path = root / "RUN.json"
            plan_path = root / "research/sprint48/PLAN.json"
            plan_path.parent.mkdir(parents=True)
            deadline = datetime.now(timezone.utc) + timedelta(hours=1)
            run_path.write_text(json.dumps({
                "status": "active",
                "final_seed_sealed": True,
                "deadline_utc": deadline.isoformat(),
                "consumed_trials": [{"status": "running"}],
                "training_branches": [],
            }))
            plan_path.write_text(json.dumps({"maximum_new_training_branches": 2}))
            with patch.object(run_branch2, "RUN_PATH", run_path), \
                    patch.object(run_branch2, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "active external trial"):
                    run_branch2.campaign_state()
                _, returned_deadline = run_branch2.campaign_state(allow_active_trial=True)
                self.assertEqual(returned_deadline, deadline)


if __name__ == "__main__":
    unittest.main()
