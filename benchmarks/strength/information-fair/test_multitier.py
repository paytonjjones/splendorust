"""Extra boundary coverage; no changes to the frozen outcome implementation."""
import unittest
from boundary import ROOT, Upstream, Tracker, RPC, blind_input

class MultitierTest(unittest.TestCase):
    def test_three_blind_tiers_and_public_reservation_memory(self):
        u=Upstream(); rpc=RPC([ROOT/'target/release/examples/native_policy_worker',ROOT/'research/e81/model/model.bin'])
        self.addCleanup(rpc.close)
        initial=u.setup(4893000000)
        observations=[]; boards=[]; full=[]
        for seed in range(100,120):
            state=initial.copy(); seat=0; tracker=Tracker(u,state)
            for turn,action in enumerate([24,30,25,31,26]):
                child,nxt=u.apply(state,seat,action,seed+turn,deterministic=True)
                tracker.update(state,child,seat,action); state,seat=child,nxt
            o=tracker.snapshot(state,seat)
            self.assertEqual([r['tier'] for r in o['players'][0]['reserved']],[0,1,2])
            self.assertEqual([r['card'] for r in o['players'][0]['reserved']],[255]*3)
            observations.append(o); full.append(tracker.fixture(state,seat))
            boards.append(blind_input(rpc,o,747474,u.np))
            self.assertEqual(u.legal(boards[-1],0),u.legal(state,seat))
        self.assertTrue(all(o==observations[0] for o in observations))
        self.assertTrue(any(f!=full[0] for f in full[1:]))
        self.assertTrue(all(u.np.array_equal(b,boards[0]) for b in boards))
        # An actor's new public reserve and its public refill remain unchanged
        # in the sampled board even while three opponent cards stay hidden.
        child,nxt=u.apply(state,seat,12,565656,deterministic=True)
        tracker.update(state,child,seat,12)
        o=tracker.snapshot(child,nxt,viewer=seat)
        # A non-acting viewer's own private/public information is preserved too.
        sample=rpc.call(op='sample',observation=o,seed=838383)
        self.assertEqual(sample['observation'],o)
        self.assertTrue(o['players'][seat]['reserved'][0]['public'])

if __name__=='__main__': unittest.main()
