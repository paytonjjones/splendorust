import copy
import gzip
import json
import math
import unittest
from types import SimpleNamespace

from collect_evidence import ROOT, record_interval
from promote import completion_evidence, decision, setup_seed, validate_stage


def synthetic_report():
    """Structurally valid all-candidate-wins evidence for gate unit tests only."""
    report = json.loads(gzip.decompress((ROOT / 'docs/results/settings-smoke.json.gz').read_bytes()))
    report['engine'] = 'splendorust-v2'
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
    def test_stage_checks_requested_nondefault_depth(self):
        report = synthetic_report()
        args = stage_args()
        args.depth = 16
        report['run_config']['search']['depth'] = 16
        validate_stage(report, args, 1000, 42, None)
        args.depth = 8
        with self.assertRaises(ValueError):
            validate_stage(report, args, 1000, 42, None)

    def test_standalone_decision_requires_current_engine_and_source_identity(self):
        for engine, source in [('splendorust-v1', 'old-source'),
                               ('future-engine', 'source'),
                               ('splendorust-v2', None),
                               ('splendorust-v2', ''),
                               ('splendorust-v2', 42)]:
            report = synthetic_report()
            report.update(engine=engine, source_id=source)
            self.assertEqual(decision(report, 2, 0.01, 10),
                             'reject: unsupported engine or missing source identity')

    def test_promotion_requires_bounded_reproducible_fast_and_better(self):
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
        self.assertEqual(decision(incomplete, 2, 0.01, 10), 'reject: decision-limit games')
        timed = copy.deepcopy(report)
        timed['reproducible'] = False
        timed['run_config']['search']['time_budget'] = {'secs': 0, 'nanos': 1}
        self.assertEqual(decision(timed, 2, 0.01, 10), 'reject: nondeterministic search budget')

    def blocked_report(self, count=1, status='no_legal_action'):
        report = synthetic_report()
        for r in report['records'][:count]:
            r.update(status=status, winners=0, ranks=[0, 0])
        report.update(completed_games=1000-count, incomplete_games=count)
        report['agents'][0]['ci95'] = record_interval(report['records'], 2, 0)
        return report

    def test_rare_no_action_uses_all_requested_games_without_inventing_winner(self):
        report = self.blocked_report()
        before = copy.deepcopy(report)
        self.assertEqual(decision(report, 2, 0.01, 10), 'promote')
        evidence = completion_evidence(report)
        self.assertEqual(evidence['candidate_credit_bounds'], [0.999, 1.0])
        self.assertEqual(evidence['max_no_action_games'], 10)
        self.assertIsNone(evidence['rejection'])
        self.assertEqual(report, before)
        self.assertLess(report['agents'][0]['ci95'][0], synthetic_report()['agents'][0]['ci95'][0])

    def test_strict_mode_excessive_blocks_and_caps_reject(self):
        self.assertEqual(decision(self.blocked_report(), 2, 0.01, 10, 0),
                         'reject: no-action fraction exceeds policy')
        self.assertEqual(decision(self.blocked_report(11), 2, 0.01, 10),
                         'reject: no-action fraction exceeds policy')
        self.assertEqual(decision(self.blocked_report(10), 2, 0.01, 10), 'promote')
        self.assertEqual(decision(self.blocked_report(status='decision_limit'), 2, 0.01, 10, 1),
                         'reject: decision-limit games')

    def test_no_action_tolerance_cannot_turn_weak_evidence_into_promotion(self):
        report = self.blocked_report()
        for r in report['records'][1:]:
            winner = r['block'] % 2
            r.update(winners=1 << r['seats'].index(winner),
                     ranks=[1 if x == winner else 2 for x in r['seats']])
        report['agents'][0]['ci95'] = record_interval(report['records'], 2, 0)
        self.assertTrue(decision(report, 2, 0.01, 10).startswith('retain'))

    def test_all_blocked_outcomes_have_no_supported_strength(self):
        report = self.blocked_report(1000)
        self.assertEqual(report['agents'][0]['ci95'], [0, 1])
        self.assertEqual(completion_evidence(report, 1)['candidate_credit_bounds'], [0, 1])
        self.assertTrue(decision(report, 2, 0.01, 10, 1).startswith('retain'))

    def test_rare_blocked_screen_proceeds_to_fresh_confirmation_and_records_policy(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        def fake_compare(command, **kwargs):
            report = self.blocked_report()
            seed = int(command[command.index('--seed') + 1])
            report['seed'] = report['run_config']['seed'] = seed
            for r in report['records']:
                r['seed'] = setup_seed(seed, r['block'])
            pathlib.Path(command[command.index('--output') + 1]).write_text(json.dumps(report))
            return SimpleNamespace(returncode=1)
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / 'run'
            with patch('promote.run'), patch('promote.build_release', return_value=ROOT / 'mock-splendor'), \
                    patch('promote.subprocess.run', side_effect=fake_compare) as compare:
                result = main(['--candidate', 'search', '--baseline', 'strong', '--screen', '1000',
                               '--confirm', '1000', '--seed', '42', '--output', str(output)])
            self.assertEqual(result, 0)
            self.assertEqual(compare.call_count, 2)
            self.assertEqual(json.loads((output/'confirm.json').read_text())['seed'], 1_000_000_042)
            saved = json.loads((output/'decision.json').read_text())
            manifest = json.loads((output/'run.json').read_text())
            self.assertEqual(saved['stage'], 'confirm')
            self.assertEqual(saved['completion']['policy'], manifest['completion_policy'])
            self.assertEqual(saved['completion']['candidate_credit_bounds'], [0.999, 1.0])
            self.assertEqual(saved['completion']['status_counts']['no_legal_action'], 1)
            for stage in ('screen', 'confirm'):
                record = json.loads((output/f'{stage}.json').read_text())['records'][0]
                self.assertEqual((record['status'], record['winners'], record['ranks']),
                                 ('no_legal_action', 0, [0, 0]))
                self.assertTrue((output/f'{stage}-completion.json').exists())

    def test_error_exit_cannot_be_hidden_by_a_valid_partial_report(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        def fake_compare(command, **kwargs):
            pathlib.Path(command[command.index('--output') + 1]).write_text(json.dumps(self.blocked_report()))
            return SimpleNamespace(returncode=7)
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)/'run'
            with patch('promote.run'), patch('promote.build_release', return_value=ROOT/'mock-splendor'), \
                    patch('promote.subprocess.run', side_effect=fake_compare):
                result = main(['--candidate', 'search', '--baseline', 'strong', '--screen', '1000',
                               '--seed', '42', '--output', str(output)])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads((output/'decision.json').read_text())['decision'],
                             'reject: execution failure')

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
                       lambda r: r.update(engine='splendorust-v1'),
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

    def test_gate_uses_executable_reported_by_cargo(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        report = synthetic_report()
        report['agents'][0]['ci95'] = [0.99, 1.0]
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory).resolve() / 'custom-target' / 'splendor'
            binary.parent.mkdir()
            binary.write_bytes(b'test executable')
            output = pathlib.Path(directory) / 'run'
            artifact = dict(reason='compiler-artifact', target=dict(name='splendor', kind=['bin']),
                            executable=str(binary), profile=dict(test=False))
            def fake_process(command, **kwargs):
                if command[0] == 'cargo':
                    return SimpleNamespace(returncode=0, stdout=json.dumps(artifact) + '\n')
                self.assertEqual(pathlib.Path(command[0]), binary)
                pathlib.Path(command[command.index('--output') + 1]).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            with patch('promote.run') as run, patch('promote.subprocess.run', side_effect=fake_process):
                result = main(['--candidate', 'search', '--baseline', 'strong', '--screen', '1000',
                               '--confirm', '1000', '--seed', '42', '--output', str(output)])
            self.assertEqual(result, 2)
            benchmark = [call.args[0] for call in run.call_args_list if 'benchmark' in call.args[0]]
            self.assertEqual(pathlib.Path(benchmark[0][0]), binary)

    def test_build_rejects_missing_ambiguous_and_failed_artifacts(self):
        import pathlib
        import subprocess
        import tempfile
        from unittest.mock import patch
        from promote import build_release
        good = dict(reason='compiler-artifact', target=dict(name='splendor', kind=['bin']),
                    executable='/unused/splendor', profile=dict(test=False))
        variants = [[], [{**good, 'executable': None}],
                    [{**good, 'target': dict(name='other', kind=['bin'])}],
                    [{**good, 'profile': dict(test=True)}],
                    [good, {**good, 'executable': '/other/splendor'}]]
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            for messages in variants:
                raw = '\n'.join(map(json.dumps, messages))
                with patch('promote.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=raw)):
                    with self.assertRaises(RuntimeError):
                        build_release(output)
                self.assertFalse((output / 'build.json').exists())
            with patch('promote.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')):
                with self.assertRaises(subprocess.CalledProcessError):
                    build_release(output)

    def test_screen_only_decides_without_confirmation(self):
        import pathlib
        import tempfile
        from unittest.mock import patch
        from promote import main
        for promote_candidate in [True, False]:
            report = synthetic_report()
            if not promote_candidate:
                for record in report['records']:
                    winner = record['block'] % 2
                    record['winners'] = 1 << record['seats'].index(winner)
                    record['ranks'] = [1 if seat == winner else 2 for seat in record['seats']]
                    record['scores'] = [15 if seat == winner else 0 for seat in record['seats']]
                report['agents'][0]['ci95'] = record_interval(report['records'], 2, 0)
            def fake_compare(command, **kwargs):
                pathlib.Path(command[command.index('--output') + 1]).write_text(json.dumps(report))
                return SimpleNamespace(returncode=0)
            with tempfile.TemporaryDirectory() as directory:
                output = pathlib.Path(directory) / 'run'
                with patch('promote.run'), patch('promote.build_release', return_value=ROOT / 'mock-splendor'), \
                        patch('promote.subprocess.run', side_effect=fake_compare) as compare:
                    result = main(['--candidate', 'search', '--baseline', 'strong', '--screen', '1000',
                                   '--confirm', '0', '--seed', '42', '--output', str(output)])
                self.assertEqual(result, 0 if promote_candidate else 2)
                self.assertEqual(compare.call_count, 1)
                self.assertFalse((output / 'confirm.json').exists())
                saved = json.loads((output / 'decision.json').read_text())
                self.assertEqual(saved['stage'], 'screen')
                self.assertEqual(saved['decision'], 'promote' if promote_candidate else 'retain baseline: benefit not confirmed')

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
            with patch('promote.run'), patch('promote.build_release', return_value=ROOT / 'mock-splendor'), \
                    patch('promote.subprocess.run', side_effect=fake_compare) as compare:
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
            for extra in [['--min-games-per-second', 'nan'], ['--min-games-per-second', 'inf'], ['--iterations', '-1'],
                          ['--max-no-action-fraction', 'nan'], ['--max-no-action-fraction', 'inf'],
                          ['--max-no-action-fraction', '-0.1'], ['--max-no-action-fraction', '1.1']]:
                with patch('promote.run') as run, self.assertRaises(SystemExit):
                    main(['--output', str(output), *extra])
                run.assert_not_called()
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
