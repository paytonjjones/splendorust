import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import resources


class Resources(unittest.TestCase):
    def test_default_requires_no_new_measurements(self):
        self.assertEqual(resources.evaluation_resources(32), {'eval_threads': 32})

    def test_worker_change_requires_parity_and_measured_gain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'local/research/training-strategy/resource-scaling/complete.json'
            path.parent.mkdir(parents=True)
            result = dict(whole_game_parity=True, excluded_from_learning_and_strength=True, results={
                'arena-32': dict(record_set_sha256='a', source_id='same', runtime_seconds=200),
                'arena-64': dict(record_set_sha256='a', source_id='same', runtime_seconds=100)})
            with patch.object(resources, 'ROOT', root):
                path.write_text(json.dumps(result))
                self.assertEqual(resources.evaluation_resources(64)['measured_shared_host_arena_speedup'], 2)
                result['results']['arena-64']['record_set_sha256'] = 'different'
                path.write_text(json.dumps(result))
                with self.assertRaises(AssertionError): resources.evaluation_resources(64)
                result['results']['arena-64']['record_set_sha256'] = 'a'
                result['results']['arena-64']['runtime_seconds'] = 195
                path.write_text(json.dumps(result))
                with self.assertRaises(AssertionError): resources.evaluation_resources(64)


if __name__ == '__main__':
    unittest.main()
