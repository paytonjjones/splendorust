import copy
import math
import unittest

from compare_budgets import bounded_interval, compare, credit_bounds
from test_promote import synthetic_report


class PairedBudgetTests(unittest.TestCase):
    def test_exact_differences_cluster_rotations(self):
        before = synthetic_report()
        after = copy.deepcopy(before)
        after['run_config']['search']['iterations'] = 256
        for record in after['records']:
            winner = record['seats'].index(1)
            record['winners'] = 1 << winner
            record['ranks'] = [1 if seat == winner else 2 for seat in range(2)]
        result = compare(before, after)
        self.assertEqual(result['independent_blocks'], 500)
        self.assertEqual(result['mean_difference_bounds'], [-1, -1])
        self.assertAlmostEqual(result['paired_ci95'][1], -1 + 14 * math.log(80) / (3 * 499))
        self.assertEqual(result['paired_ci95'][0], -1)

    def test_unfinished_outcomes_are_bounded_not_dropped(self):
        before = synthetic_report()
        after = copy.deepcopy(before)
        for record in after['records']:
            record.update(status='no_legal_action', winners=0, ranks=[0, 0])
        after.update(completed_games=0, incomplete_games=1000)
        result = compare(before, after)
        self.assertEqual(result['mean_difference_bounds'], [-1, 0])
        self.assertEqual(result['unfinished_games'], [0, 1000])
        self.assertGreater(result['paired_ci95'][1], 0)
        self.assertEqual(compare(after, after)['paired_ci95'], [-1, 1])

    def test_shared_credit_uses_identity_and_winner_count(self):
        base = dict(status='complete', seats=[1, 0, 2], winners=6)
        self.assertEqual(credit_bounds(base), (0.5, 0.5))
        self.assertEqual(credit_bounds({**base, 'winners': 1}), (0, 0))
        self.assertEqual(bounded_interval([0], 0.05), [-1, 1])

    def test_rejects_unpaired_or_different_configuration(self):
        before = synthetic_report()
        for mutate in [lambda r: r.update(source_id='different'),
                       lambda r: r['run_config']['search'].update(depth=9),
                       lambda r: [g.update(seed=g['seed']+1) for g in r['records']]]:
            after = copy.deepcopy(before)
            mutate(after)
            with self.assertRaises(ValueError):
                compare(before, after)


if __name__ == '__main__':
    unittest.main()
