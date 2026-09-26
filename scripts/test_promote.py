import copy
import gzip
import json
import math
import unittest
from types import SimpleNamespace

from collect_evidence import ROOT, record_interval
from promote import decision, setup_seed, validate_stage


def synthetic_report():
    """Structurally valid all-candidate-wins evidence for gate unit tests only."""
    report = json.loads(gzip.decompress((ROOT / 'docs/results/settings-smoke.json.gz').read_bytes()))
    config = report['run_config']
    config.update(games=1000, seed=42, threads=4, check=False)
    config['search'].update(iterations=128, depth=8, width=6)
    report.update(requested_games=1000, completed_games=1000, incomplete_games=0,
                  independent_blocks=500, seed=42, threads=4, invariants_checked=False,
                  runtime_seconds=10.0, games_per_second=100.0)
    records = []
    for i in range(1000):
        block, rotation = divmod(i, 2)
        seats = [rotation, 1-rotation]
        records.append(dict(block=block, rotation=rotation, seed=setup_seed(42, block), seats=seats,
                            scores=[15 if x == 0 else 0 for x in seats],
                            ranks=[1 if x == 0 else 2 for x in seats], winners=1 << seats.index(0),
                            turns=50, decisions=80, status='complete', trajectory_hash='0000000000000000'))
    report['records'] = records
    for agent in report['agents']:
        agent['ci95'] = record_interval(records, 2, agent['identity'])
    return report


def stage_args():
    return SimpleNamespace(candidate='search', baseline='strong', players=2, threads=4, iterations=128)


class GateTests(unittest.TestCase):
    def test_promotion_requires_complete_reproducible_fast_and_better(self):
        report = synthetic_report()
        expected_lower = 1 - 7 * math.log(80) / (3 * 499)
        self.assertAlmostEqual(report['agents'][0]['ci95'][0], expected_lower)
        self.assertEqual(decision(report, 2, 0.01, 10), 'promote')
        self.assertEqual(decision(report, 2, 0.01, 101), 'reject: throughput floor')
        self.assertTrue(decision(report, 2, 0.49, 10).startswith('retain'))
        incomplete = copy.deepcopy(report)
        incomplete['records'][0].update(status='decision_limit', winners=0, ranks=[0, 0])
        incomplete.update(completed_games=999, incomplete_games=1)
        incomplete['agents'][0]['ci95'] = record_interval(incomplete['records'], 2, 0)
        self.assertEqual(decision(incomplete, 2, 0.01, 10), 'reject: incomplete games')
        timed = copy.deepcopy(report)
        timed['reproducible'] = False
        timed['run_config']['search']['time_budget'] = {'secs': 0, 'nanos': 1}
        self.assertEqual(decision(timed, 2, 0.01, 10), 'reject: nondeterministic search budget')

    def test_corrupt_records_or_summaries_cannot_promote(self):
        mutations = [
            lambda r: r['records'].pop(),
            lambda r: r['records'][0].update(winners=0),
            lambda r: r['records'][1].update(rotation=0),
            lambda r: r['records'][0].update(status='decision_limit'),
            lambda r: r['agents'].reverse(),
            lambda r: r['agents'][0].update(ci95=[0.99, 1.0]),
            lambda r: r.update(runtime_seconds=1),
            lambda r: r.update(incomplete_games=1),
        ]
        for mutate in mutations:
            report = synthetic_report()
            mutate(report)
            self.assertTrue(decision(report, 2, 0.01, 10).startswith('reject: invalid report evidence'))

    def test_stage_requires_exact_settings_seed_schedule_and_source(self):
        report = synthetic_report()
        source = validate_stage(report, stage_args(), 1000, 42, None)
        self.assertEqual(source, (report['engine'], report['source_id']))
        self.assertEqual(setup_seed(0, 0), 16294208416658607535)
        raw = json.loads(gzip.decompress((ROOT / 'docs/results/settings-smoke.json.gz').read_bytes()))
        for game in raw['records']:
            self.assertEqual(game['seed'], setup_seed(raw['seed'], game['block']))
        for mutate in [lambda r: r['run_config']['search'].update(iterations=127),
                       lambda r: r.update(run_config=None),
                       lambda r: r.update(engine='future-engine'),
                       lambda r: r.update(source_id='other-source'),
                       lambda r: [g.update(seed=0) for g in r['records'][:2]]]:
            bad = copy.deepcopy(report)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_stage(bad, stage_args(), 1000, 42, source)
        with self.assertRaises(ValueError):
            validate_stage(report, stage_args(), 1000, 43, None)

    def test_three_player_shared_wins_keep_rotations_clustered(self):
        records = []
        # Every game is a three-way shared win; one independent setup block.
        for rotation in range(3):
            records.append({'seats': [(seat + rotation) % 3 for seat in range(3)],
                            'status': 'complete', 'winners': 7})
        self.assertEqual(record_interval(records, 3, 0), [0, 1])
        # Repeated synthetic blocks have constant 1/3 credit, not three wins.
        many = records * 1000
        half = 7 * math.log(80) / (3 * 999)
        low, high = record_interval(many, 3, 0)
        self.assertAlmostEqual(low, 1/3 - half)
        self.assertAlmostEqual(high, 1/3 + half)
        unknown = [{'seats': r['seats'], 'status': 'decision_limit', 'winners': 0} for r in many]
        self.assertEqual(record_interval(unknown, 3, 0), [0, 1])

    def test_bad_screen_never_runs_confirmation(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        report = synthetic_report()
        report['agents'][0]['ci95'] = [0.99, 1.0]
        def fake_compare(command, **kwargs):
            pathlib.Path(command[command.index('--output') + 1]).write_text(json.dumps(report))
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'run'
            with patch('promote.run'), patch('promote.subprocess.run', side_effect=fake_compare) as compare:
                result = main(['--candidate', 'search', '--baseline', 'strong', '--screen', '1000',
                               '--confirm', '1000', '--seed', '42', '--output', str(output)])
            self.assertEqual(result, 2)
            self.assertEqual(compare.call_count, 1)
            self.assertFalse((output / 'confirm.json').exists())
            saved = json.loads((output / 'decision.json').read_text())
            self.assertIn('interval disagrees', saved['decision'])
            manifest = json.loads((output / 'run.json').read_text())
            self.assertEqual(saved['evidence_tools_sha256'], manifest['evidence_tools_sha256'])
            self.assertEqual(set(saved['evidence_tools_sha256']), {'promote.py', 'collect_evidence.py'})
            self.assertTrue(all(len(value) == 64 for value in saved['evidence_tools_sha256'].values()))


class EvidenceSafetyTests(unittest.TestCase):
    def test_nonfinite_or_invalid_evidence_cannot_promote(self):
        report = synthetic_report()
        for rate in [math.nan, math.inf, -1]:
            with self.subTest(rate=rate):
                self.assertTrue(decision({**report, 'games_per_second': rate}, 2, 0.01, 10).startswith('reject'))
        for interval in [[math.nan, 0.7], [0.6, math.inf], [0.8, 0.7], [0.6, 1.1]]:
            bad = copy.deepcopy(report)
            bad['agents'][0]['ci95'] = interval
            self.assertTrue(decision(bad, 2, 0.01, 10).startswith('reject'))

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
