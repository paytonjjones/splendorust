import unittest
from promote import decision

class GateTests(unittest.TestCase):
    def test_promotion_requires_complete_reproducible_fast_and_better(self):
        r={'incomplete_games':0,'reproducible':True,'games_per_second':100,
           'agents':[{'ci95':[0.55,0.65]}]}
        self.assertEqual(decision(r,2,0.01,10),'promote')
        for key,value in [('incomplete_games',1),('reproducible',False),('games_per_second',1)]:
            bad=dict(r);bad[key]=value
            self.assertTrue(decision(bad,2,0.01,10).startswith('reject'))
        self.assertTrue(decision(r,2,0.1,10).startswith('retain'))



class EvidenceSafetyTests(unittest.TestCase):
    def test_nonfinite_or_invalid_evidence_cannot_promote(self):
        import math
        r = {'incomplete_games': 0, 'reproducible': True, 'games_per_second': 100,
             'agents': [{'ci95': [0.6, 0.7]}]}
        for rate in [math.nan, math.inf, -1]:
            with self.subTest(rate=rate):
                self.assertTrue(decision({**r, 'games_per_second': rate}, 2, 0.01, 10).startswith('reject'))
        for interval in [[math.nan, 0.7], [0.6, math.inf], [0.8, 0.7], [0.6, 1.1]]:
            with self.subTest(interval=interval):
                self.assertTrue(decision({**r, 'agents': [{'ci95': interval}]}, 2, 0.01, 10).startswith('reject'))

    def test_existing_run_cannot_be_overwritten(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        with tempfile.TemporaryDirectory() as directory:
            evidence = pathlib.Path(directory) / 'decision.json'
            evidence.write_text('{"decision":"promote"}\n')
            with patch('promote.run') as run, self.assertRaises(SystemExit):
                main(['--output', directory])
            run.assert_not_called()
            self.assertEqual(evidence.read_text(), '{"decision":"promote"}\n')

    def test_failed_check_records_rejection_and_parameters(self):
        import json
        import pathlib
        import subprocess
        import tempfile
        from unittest.mock import patch
        from promote import main
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'new-run'
            with patch('promote.run', side_effect=subprocess.CalledProcessError(1, ['cargo', 'fmt'])):
                self.assertEqual(main(['--output', str(output)]), 2)
            self.assertEqual(json.loads((output / 'decision.json').read_text())['decision'], 'reject: execution failure')
            self.assertEqual(json.loads((output / 'run.json').read_text())['confirmation_seed'], 1_000_012_345)

    def test_bad_numeric_arguments_fail_before_creating_output(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'new-run'
            for extra in [['--min-games-per-second', 'nan'], ['--min-games-per-second', 'inf'], ['--iterations', '-1']]:
                with patch('promote.run') as run, self.assertRaises(SystemExit):
                    main(['--output', str(output), *extra])
                run.assert_not_called()
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
