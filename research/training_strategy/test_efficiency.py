"""Synthetic accounting fixtures; these are not engine or strength games."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from data import DTYPE, prepare
from efficiency_data import assemble


def chunk(path, seed):
    path.mkdir()
    rows = np.zeros(4, dtype=DTYPE)
    rows['setup'] = [seed, seed, seed + 1, seed + 1]
    rows['decision'] = [0, 1, 0, 1]
    rows['seat'] = [0, 1, 0, 1]
    rows['full'] = [1, 0, 1, 0]
    rows['mask'][:, 0] = 1
    rows['visits'][:, 0] = [256, 64, 256, 64]
    rows['q'].fill(np.nan)
    rows['q'][:, 0] = .75
    rows['root'] = .75
    rows['network'] = .5
    rows['outcome'] = [1, 0, np.nan, np.nan]
    rows.tofile(path / 'rows.bin')
    records = []
    for game, status in enumerate(['complete', 'decision_limit']):
        records.append(dict(game=game, status=status, winners=1 if game == 0 else 0,
                            history=dict(seed=seed + game, actions=[[0] * 7, [0] * 7]),
                            rows=2, full_rows=1, simulations=320, inferences=300))
    (path / 'histories.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
    completion = dict(cheap_iterations=64, depth=16, engine='accounting-fixture',
                      full_probability=.25, iterations=256, row_bytes=2600,
                      stochastic_turns=0, threads=32, world_pool=3, all_games_replayed=True,
                      counts=[1, 0, 1], games=2, rows=4, full_rows=2, simulations=640,
                      inferences=600, seconds=2., seed=seed, policy_seed=seed + 10)
    (path / 'complete.json').write_text(json.dumps(completion))
    return rows


class ChunkAccounting(unittest.TestCase):
    def test_join_preserves_labels_bytes_exclusions_and_paid_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            chunk(root / 'a', 100)
            chunk(root / 'b', 200)
            expected = (root / 'a/rows.bin').read_bytes() + (root / 'b/rows.bin').read_bytes()
            receipt = assemble([root / 'a', root / 'b'], root / 'joined')
            self.assertEqual((root / 'joined/rows.bin').read_bytes(), expected)
            self.assertEqual(receipt['counts'], [2, 0, 2])
            self.assertEqual(receipt['inferences'], 1200)
            self.assertEqual(receipt['simulations'], 1280)
            self.assertEqual(receipt['seconds'], 4.)
            rows, _, eligible, _ = prepare(root / 'joined')
            self.assertEqual(eligible.tolist(), [0, 4])
            self.assertEqual(int(np.isnan(rows['outcome']).sum()), 4)
            records = [json.loads(line) for line in (root / 'joined/histories.jsonl').read_text().splitlines()]
            self.assertEqual([r['game'] for r in records], [0, 1, 2, 3])

    def test_duplicate_setups_fail_before_combined_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            chunk(root / 'a', 100)
            chunk(root / 'b', 100)
            with self.assertRaisesRegex(AssertionError, 'share setup IDs'):
                assemble([root / 'a', root / 'b'], root / 'joined')
            self.assertFalse((root / 'joined').exists())

    def test_excluded_only_chunk_retains_its_paid_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            chunk(root / 'a', 100)
            chunk(root / 'b', 200)
            rows = np.memmap(root / 'b/rows.bin', mode='r+', dtype=DTYPE)
            rows['full'] = 0
            rows['visits'][:, 0] = 64
            rows.flush()
            del rows
            history = root / 'b/histories.jsonl'
            records = [json.loads(line) for line in history.read_text().splitlines()]
            for record in records:
                record['full_rows'] = 0
                record['simulations'] = 128
                record['inferences'] = 120
            history.write_text(''.join(json.dumps(record) + '\n' for record in records))
            path = root / 'b/complete.json'
            receipt = json.loads(path.read_text())
            receipt.update(full_rows=0, simulations=256, inferences=240)
            path.write_text(json.dumps(receipt))
            result = assemble([root / 'a', root / 'b'], root / 'joined')
            self.assertEqual(result['inferences'], 840)
            self.assertEqual(result['counts'], [2, 0, 2])
            self.assertEqual(prepare(root / 'joined')[2].tolist(), [0])

    def test_changed_cap_and_wrong_terminal_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            chunk(root / 'a', 100)
            chunk(root / 'b', 200)
            path = root / 'b/complete.json'
            receipt = json.loads(path.read_text())
            receipt['cheap_iterations'] = 32
            path.write_text(json.dumps(receipt))
            with self.assertRaises(AssertionError):
                assemble([root / 'a', root / 'b'], root / 'joined')
            rows = np.memmap(root / 'a/rows.bin', mode='r+', dtype=DTYPE)
            rows['outcome'][0] = 0
            rows.flush()
            del rows
            with self.assertRaises(AssertionError):
                assemble([root / 'a'], root / 'wrong')
            self.assertFalse((root / 'wrong/complete.json').exists())


if __name__ == '__main__':
    unittest.main()
