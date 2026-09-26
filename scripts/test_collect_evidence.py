import gzip
import json
import pathlib
import tempfile
import unittest

from collect_evidence import ROOT, collect


class ArchiveTests(unittest.TestCase):
    def test_index_preserves_engine_and_nullable_historical_source(self):
        current = gzip.decompress((ROOT / 'docs/results/capacity-after.json.gz').read_bytes())
        collect([self.report('old'), self.report('current', current)], self.output)
        index = {r['name']: r for r in json.loads((self.output / 'index.json').read_text())}
        self.assertEqual(index['old']['engine'], 'splendorust-v1')
        self.assertIsNone(index['old']['source_id'])
        self.assertEqual(index['current']['engine'], 'splendorust-v2')
        self.assertEqual(index['current']['source_id'], json.loads(current)['source_id'])
        self.assertEqual(gzip.decompress((self.output / 'old.json.gz').read_bytes()), self.raw)
        self.assertEqual(gzip.decompress((self.output / 'current.json.gz').read_bytes()), current)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.output = self.root / 'archive'
        self.output.mkdir()
        # Real checked report, including paired records and source metadata.
        self.raw = gzip.decompress((ROOT / 'docs/results/strong-v1-confirm.json.gz').read_bytes())

    def report(self, name, raw=None):
        path = self.root / (name + '.json')
        path.write_bytes(self.raw if raw is None else raw)
        return path

    def test_empty_input_preserves_index_exactly(self):
        index = self.output / 'index.json'
        content = '[{"name":"prior","records_sha256":"abc"}]\n'
        index.write_text(content)
        self.assertEqual(collect([], self.output), 0)
        self.assertEqual(index.read_text(), content)

    def test_new_report_preserves_previous_entries_and_raw_bytes(self):
        first = self.report('first')
        second = self.report('second')
        collect([first], self.output)
        collect([second], self.output)
        index = json.loads((self.output / 'index.json').read_text())
        self.assertEqual([entry['name'] for entry in index], ['first', 'second'])
        self.assertEqual(gzip.decompress((self.output / 'first.json.gz').read_bytes()), self.raw)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        collect([first, second], self.output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_conflict_rejects_batch_without_writes(self):
        original = self.report('z-original')
        collect([original], self.output)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        changed = json.loads(self.raw)
        changed['runtime_seconds'] += 1
        original.write_text(json.dumps(changed))
        with self.assertRaisesRegex(FileExistsError, 'archive differs'):
            collect([self.report('a-new'), original], self.output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_structured_settings_reject_conflicts_before_writing(self):
        raw = gzip.decompress((ROOT / 'docs/results/settings-smoke.json.gz').read_bytes())
        self.assertEqual(collect([self.report('settings', raw)], self.output), 1)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        mutations = [
            lambda r: r['run_config'].update(seed=0),
            lambda r: r['run_config'].update(names=['strong', 'search']),
            lambda r: r['run_config'].update(threads=True),
            lambda r: r['run_config'].update(check=False),
            lambda r: r['run_config']['search'].update(iterations=-1),
            lambda r: r['run_config']['search'].update(depth=2**32),
            lambda r: r['run_config']['search'].update(rollout='unknown'),
            lambda r: r['run_config']['search'].update(time_budget={'secs': 0, 'nanos': 10**9}),
            lambda r: r['run_config']['search'].update(time_budget={'secs': 0, 'nanos': 1}),
            lambda r: r['run_config']['search'].update(typo=1),
            lambda r: r.update(reproducible=False),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                report = json.loads(raw)
                mutate(report)
                with self.assertRaisesRegex(ValueError, 'run settings'):
                    collect([self.report('a-new'), self.report('z-bad', json.dumps(report).encode())], self.output)
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})
        timed = json.loads(raw)
        timed['run_config']['search']['time_budget'] = {'secs': 0, 'nanos': 123}
        timed['reproducible'] = False
        self.assertEqual(collect([self.report('timed', json.dumps(timed).encode())], self.output), 1)

    def test_malformed_reports_fail_before_any_batch_write(self):
        mutations = [
            lambda r: r['records'].pop(),
            lambda r: r['records'][1].update(seed=0),
            lambda r: r['records'][1].update(rotation=0),
            lambda r: r['records'][1].update(seats=[0, 1]),
            lambda r: r.update(completed_games=0),
            lambda r: [g.update(seed=r['records'][0]['seed']) for g in r['records'][2:4]],
            lambda r: r['records'][0].update(status='decision_limit'),
            lambda r: r['records'][0].update(winners=0),
        ]
        for mutate in mutations:
            report = json.loads(self.raw)
            mutate(report)
            bad = self.report('z-bad', json.dumps(report).encode())
            with self.assertRaises(ValueError):
                collect([self.report('a-good'), bad], self.output)
            self.assertEqual(list(self.output.iterdir()), [])



if __name__ == '__main__':
    unittest.main()
