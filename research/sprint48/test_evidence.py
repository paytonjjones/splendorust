"""Guard the missing-outcome and paired-sample boundary used by final evidence."""
import copy
import math
import unittest
from evidence import summarize


def fixture(blocks=500):
    rows = []
    for block in range(blocks):
        for rotation in (0, 1):
            rows.append(dict(index=2 * block + rotation, rotation=rotation, block=block,
                setup_seed=block, initial_state=[block], status='complete',
                seats=['champion', 'alphazero'] if rotation == 0 else ['alphazero', 'champion'],
                rewards=[1, 0] if rotation == 0 else [0, 1], native_rewards=[1, -1],
                termination='native_score'))
    return {'games':len(rows)}, rows


class EvidenceTests(unittest.TestCase):
    def test_rotations_are_one_independent_sample(self):
        meta, rows = fixture()
        result = summarize(meta, rows)
        self.assertEqual(result['setup_blocks'], 500)
        self.assertAlmostEqual(result['radius'], math.sqrt(math.log(40) / 1000))
        self.assertTrue(result['decisive_native_criterion'])
        rows[1]['setup_seed'] = 9999
        with self.assertRaises(ValueError):
            summarize(meta, rows)

    def test_caps_unknown_changes_only_sensitivity(self):
        meta, rows = fixture()
        original = copy.deepcopy(rows)
        for row in rows:
            row['termination'] = 'native_turn_cap'
        result = summarize(meta, rows)
        self.assertTrue(result['decisive_native_criterion'])
        self.assertEqual(result['caps_as_unknown_credit_bounds'], [0, 1])
        self.assertFalse(result['decisive_with_caps_unknown'])
        self.assertEqual(rows[0]['rewards'], original[0]['rewards'])

    def test_unknown_and_shared_credit_keep_full_denominator(self):
        meta, rows = fixture()
        rows[0].update(status='no_legal_action', rewards=None, native_rewards=None, termination='unknown')
        rows[1]['rewards'] = [.5, .5]
        result = summarize(meta, rows)
        self.assertEqual(result['games'], 1000)
        self.assertEqual(result['all_requested_credit_bounds'], [.9985, .9995])
        self.assertFalse(result['evidence_rejections'])
        for row in rows[2:14]:
            row.update(status='decision_limit', rewards=None, native_rewards=None)
        self.assertTrue(summarize(meta, rows)['evidence_rejections'])

    def test_partial_or_duplicate_blocks_rejected(self):
        meta, rows = fixture(2)
        with self.assertRaises(ValueError):
            summarize(meta, rows[:-1])
        rows[2]['setup_seed'] = rows[3]['setup_seed'] = 0
        with self.assertRaises(ValueError):
            summarize(meta, rows)


if __name__ == '__main__':
    unittest.main()
