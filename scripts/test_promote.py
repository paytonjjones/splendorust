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

if __name__ == '__main__':
    unittest.main()
