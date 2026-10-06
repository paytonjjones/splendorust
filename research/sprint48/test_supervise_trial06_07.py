import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supervise_trial06_07 import command07, launch_trial07


class MockProcess:
    pid = 43210


class SupervisorLaunchTests(unittest.TestCase):
    def test_launch_records_exact_command_in_owned_process_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = Path(temporary) / 'queue'
            calls = []

            def fake_popen(command, **kwargs):
                calls.append((command, kwargs))
                return MockProcess()

            process = launch_trial07(queue, popen=fake_popen)
            self.assertEqual(process.pid, 43210)
            self.assertEqual(len(calls), 1)
            command, kwargs = calls[0]
            self.assertEqual(command, command07())
            self.assertTrue(kwargs['start_new_session'])
            self.assertEqual(kwargs['cwd'], Path(__file__).resolve().parents[2])
            record = json.loads((queue / 'trial07-process.json').read_text())
            self.assertEqual(record['pid'], 43210)
            self.assertEqual(record['pgid'], 43210)
            self.assertEqual(record['command'], command)
            self.assertTrue((queue / 'trial07.log').is_file())


if __name__ == '__main__':
    unittest.main()
