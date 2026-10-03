"""Verify receipt deduplication and explicit unknown process status."""
import json
import tempfile
import unittest
from pathlib import Path

from collect_costs import inventory


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class Costs(unittest.TestCase):
    def test_copied_pilot_is_counted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('original', 'copy'):
                write(root/name/'process.json', dict(pid=123, command=['collector']))
                write(root/name/'exit.json', dict(returncode=0, seconds=40))
            result = inventory([root])
            self.assertEqual(result['known_command_elapsed_seconds'], 40)
            self.assertEqual(len(result['commands']), 1)
            self.assertEqual(len(next(iter(result['commands'].values()))['receipt_locations']), 2)

    def test_adopted_collection_retains_unknown_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root/'data'
            write(corpus/'complete.json', dict(seconds=39, counts=[64, 0, 0]))
            write(root/'command/process.json', dict(pid=123,
                command=['rich_selfplay', '--output', str(corpus)]))
            result = inventory([root])
            self.assertEqual(result['known_command_elapsed_seconds'], 0)
            self.assertEqual(result['collector_reported_seconds_without_command_exit'], 39)
            self.assertEqual(len(result['commands_without_exit_receipts']), 1)
            self.assertIsNone(next(iter(result['commands'].values()))['returncode'])

    def test_service_counters_are_not_added_to_command_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('original', 'copy'):
                write(root/name/'run.json', dict(pid=123, command=['service.py']))
                write(root/name/'service.log', dict(calls=200, batches=10, seconds=40))
            result = inventory([root])
            self.assertEqual(result['known_command_elapsed_seconds'], 0)
            self.assertEqual(len(result['services']), 1)
            self.assertEqual(next(iter(result['services'].values()))['last_logged_counter']['calls'], 200)

    def test_conflicting_copied_exit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, seconds in (('original', 40), ('copy', 50)):
                write(root/name/'process.json', dict(pid=123, command=['collector']))
                write(root/name/'exit.json', dict(returncode=0, seconds=seconds))
            with self.assertRaisesRegex(AssertionError, 'Conflicting copied exits'):
                inventory([root])


if __name__ == '__main__':
    unittest.main()
