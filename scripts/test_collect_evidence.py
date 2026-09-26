import gzip
import json
import pathlib
import tempfile
import unittest

from collect_evidence import ROOT, collect


class ArchiveTests(unittest.TestCase):
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
