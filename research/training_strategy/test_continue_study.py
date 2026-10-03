"""Guard against duplicate launches and incorrect process-failure decisions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import continue_study


class WaitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / 'first'
        self.directory.mkdir()
        (self.directory / 'progress.json').write_text(json.dumps({'pid': 123}))
        self.live = dict(live=True, command=(
            'python research/training_strategy/resume_first.py --first ' + str(self.directory)))

    def test_complete_receipt_does_not_restart_a_live_controller(self):
        (self.directory / 'complete.json').write_text('{}')
        with patch.object(continue_study, 'process', side_effect=[self.live, {'live': False}]), \
             patch.object(continue_study.time, 'sleep') as sleep:
            continue_study.wait_finished(self.directory)
        sleep.assert_called_once_with(30)

    def test_dead_controller_without_terminal_receipt_stops(self):
        with patch.object(continue_study, 'process', return_value={'live': False}):
            with self.assertRaisesRegex(AssertionError, 'without completion'):
                continue_study.wait_finished(self.directory)

    def test_pid_reuse_is_not_treated_as_a_study_controller(self):
        with patch.object(continue_study, 'process', return_value={'live': True, 'command': 'unrelated'}):
            with self.assertRaises(AssertionError):
                continue_study.wait_finished(self.directory)

    def test_same_script_in_another_directory_is_rejected(self):
        other = dict(live=True, command='python research/training_strategy/resume_first.py --first /another/first')
        with patch.object(continue_study, 'process', return_value=other):
            with self.assertRaises(AssertionError):
                continue_study.wait_finished(self.directory)

    def test_truncated_progress_read_does_not_trigger_recovery(self):
        (self.directory / 'complete.json').write_text('{}')
        error = json.JSONDecodeError('partial receipt', '', 0)
        with patch.object(continue_study, 'load', side_effect=[error, {'pid': 123}]), \
             patch.object(continue_study, 'process', return_value={'live': False}), \
             patch.object(continue_study.time, 'sleep') as sleep:
            continue_study.wait_finished(self.directory)
        sleep.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
