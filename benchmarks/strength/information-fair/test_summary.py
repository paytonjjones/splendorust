import json
import tempfile
import unittest
from pathlib import Path
from boundary import ARMS, stream
from summarize import SETTINGS, summarize

class SummaryTest(unittest.TestCase):
    def fixture(self, directory, incomplete=False):
        for arm in ARMS:
            meta = {k: 1 for k in SETTINGS}
            meta.update(games=8, master=123456, information_arm=arm, wall_seconds=1)
            rows = []
            for i in range(8):
                seats = ['champion','alphazero'] if i%2==0 else ['alphazero','champion']
                credit = 0. if arm=='control' else .5 if arm=='blind-alpha' else 1.
                rewards = [credit,1-credit] if i%2==0 else [1-credit,credit]
                rows.append(dict(index=i, block=i//2, rotation=i%2, initial_state=[i//2],
                    setup_seed=stream(meta['master'],'setup',i//2),
                    policy_seeds=[stream(meta['master'],'policy',i//2,x) for x in range(2)],
                    seats=seats, status='invalid' if incomplete and i==0 else 'complete',
                    rewards=None if incomplete and i==0 else rewards,
                    termination='native_score', simulations=128, inferences=1, policy_seconds=[1,1]))
            path = directory/arm/'games.jsonl'; path.parent.mkdir(parents=True)
            path.write_text('\n'.join(map(json.dumps,[meta]+rows))+'\n')

    def test_exact_matched_differences_and_gap_fraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp); self.fixture(stage)
            result=summarize(stage,64)
            self.assertEqual(result['contrasts']['blind-alpha']['delta_credit_bounds'],[.5,.5])
            self.assertEqual(result['contrasts']['privileged-sr']['delta_credit_bounds'],[1.,1.])
            self.assertEqual(result['contrasts']['blind-alpha']['control_gap_reduced_fraction_bounds'],[1.,1.])
            self.assertEqual(result['contrasts']['blind-alpha']['paired_bootstrap95'],[.5,.5])

    def test_unknown_outcomes_retain_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp); self.fixture(stage,True)
            result=summarize(stage,64)
            self.assertEqual(result['arms']['control']['credit_bounds'],[0.,.125])
            self.assertEqual(result['arms']['control']['statuses'],{'invalid':1,'complete':7})
            self.assertEqual(result['contrasts']['blind-alpha']['delta_credit_bounds'],[.3125,.5625])

    def test_unpaired_seed_and_changed_budget_rejected(self):
        for corrupt in ['seed','budget']:
            with tempfile.TemporaryDirectory() as tmp:
                stage=Path(tmp); self.fixture(stage)
                path=stage/'blind-alpha/games.jsonl'
                meta,*rows=map(json.loads,path.read_text().splitlines())
                if corrupt=='seed': rows[0]['policy_seeds'][0]+=1
                else: meta['iterations']+=1
                path.write_text('\n'.join(map(json.dumps,[meta]+rows))+'\n')
                with self.assertRaises(AssertionError): summarize(stage,64)

if __name__=='__main__': unittest.main()
