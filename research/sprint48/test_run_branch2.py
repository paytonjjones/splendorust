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

    def test_trainer_output_exists_empty_before_mock_process_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "receipt"
            output.mkdir()
            expected_command = ["trainer", "--output", str(output / "fit")]
            expected_env = {"PYTHONUNBUFFERED": "1"}
            sentinel = object()

            def mock_popen(command, **kwargs):
                trainer_output = output / "fit"
                self.assertEqual(command, expected_command)
                self.assertTrue(trainer_output.is_dir())
                self.assertEqual(list(trainer_output.iterdir()), [])
                self.assertEqual(kwargs["cwd"], root)
                self.assertEqual(kwargs["env"], expected_env)
                return sentinel

            with patch.object(run_branch2.subprocess, "Popen", side_effect=mock_popen):
                process = run_branch2.launch_trainer(
                    expected_command, output, object(), root, expected_env)

            self.assertIs(process, sentinel)

    def test_trainer_output_must_be_new_before_process_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "receipt"
            (output / "fit").mkdir(parents=True)
            with patch.object(run_branch2.subprocess, "Popen") as popen:
                with self.assertRaises(FileExistsError):
                    run_branch2.launch_trainer(["trainer"], output, object(), root, {})
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
