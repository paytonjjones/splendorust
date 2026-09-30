import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
from lineage import provisional_decision
from test_promote import synthetic_report

def report_with_credit(wins,missing=0):
    r=synthetic_report()
    for i,g in enumerate(r['records']):
        winner=0 if i<wins else 1
        seat=g['seats'].index(winner)
        g.update(winners=1<<seat,ranks=[1 if s==seat else 2 for s in range(2)])
        if i>=1000-missing:g.update(status='no_legal_action',winners=0,ranks=[0,0])
    r.update(completed_games=1000-missing,incomplete_games=missing)
    return r

class LineageTests(unittest.TestCase):
    def test_small_positive_is_provisional_without_ci_confirmation(self):
        result=provisional_decision(report_with_credit(515))
        self.assertTrue(result['selected']);self.assertLess(result['ci95'][0],.5)
        self.assertEqual(result['requested_credit_bounds'],[.515,.515])
    def test_equal_threshold_and_negative_are_rejected(self):
        for wins in [505,500,490]:self.assertFalse(provisional_decision(report_with_credit(wins))['selected'])
    def test_unknowns_are_bounded_and_not_invented_wins(self):
        r=report_with_credit(510,500)
        result=provisional_decision(r)
        self.assertFalse(result['selected']);self.assertEqual(result['requested_credit_bounds'],[.5,1.])
    def test_forged_summary_does_not_change_record_decision(self):
        r=report_with_credit(490);r['agents'][0]['win_share']=1000
        self.assertFalse(provisional_decision(r)['selected'])
    def test_invalid_seats_and_timed_runs_are_rejected(self):
        r=report_with_credit(515);r['records'][0]['seats']=[0,0]
        with self.assertRaises(ValueError):provisional_decision(r)
        r=report_with_credit(515);r['reproducible']=False
        with self.assertRaises(ValueError):provisional_decision(r)
