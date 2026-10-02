import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from collect_evidence import record_interval
from reassess_promotion import reassess
from test_promote import synthetic_report


class ReassessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        report = synthetic_report()
        report['records'][0].update(status='no_legal_action', winners=0, ranks=[0, 0])
        report.update(completed_games=999, incomplete_games=1)
        report['agents'][0]['ci95'] = record_interval(report['records'], 2, 0)
        raw = json.dumps(report).encode()
        (self.root/'screen.json').write_bytes(raw)
        (self.root/'run.json').write_text(json.dumps(dict(candidate='search', baseline='strong',
            screen=1000, confirm=0, seed=42, threads=4, iterations=128, depth=8, players=2,
            margin=0.01, min_games_per_second=0)))
        (self.root/'decision.json').write_text(json.dumps(dict(decision='reject: incomplete games',
            stage='screen', raw_report_sha256=hashlib.sha256(raw).hexdigest(),
            record_set_sha256=hashlib.sha256(json.dumps(report['records'], sort_keys=True,
                                                       separators=(',', ':')).encode()).hexdigest())))

    def test_reassessment_keeps_original_evidence_and_requires_no_new_games(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        result = reassess(self.root)
        self.assertEqual(result['original_decision'], 'reject: incomplete games')
        self.assertEqual(result['decision'], 'promote')
        self.assertEqual(result['completion']['candidate_credit_bounds'], [0.999, 1.0])
        self.assertEqual(result['new_games'], 0)
        self.assertFalse(result['champion_changed'])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(reassess(self.root, 0)['decision'], 'reject: no-action fraction exceeds policy')

    def test_changed_raw_data_or_wrong_record_hash_cannot_be_reassessed(self):
        p = self.root/'decision.json'
        old = json.loads(p.read_text())
        for key in ('raw_report_sha256', 'record_set_sha256'):
            p.write_text(json.dumps({**old, key:'bad'}))
            with self.assertRaisesRegex(ValueError, 'hashes disagree'):
                reassess(self.root)

    def test_execution_failure_is_not_reassessed(self):
        (self.root/'decision.json').write_text('{"decision":"reject: execution failure"}')
        with self.assertRaisesRegex(ValueError, 'execution failures'):
            reassess(self.root)


if __name__ == '__main__':
    unittest.main()
