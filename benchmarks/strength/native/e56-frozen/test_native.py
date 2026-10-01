import copy
import json
import unittest
from upstream import ROOT, Upstream, Tracker, sha
from validate import RPC

class InformationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u=Upstream()
    def setUp(self):
        self.rpc=RPC([ROOT/'target/release/examples/native_policy_worker',ROOT/'research/e56/model/model.bin'])
        self.addCleanup(self.rpc.close)
    def reset(self):
        self.rpc.call(op='reset',seed=5100000000,iterations=128,depth=16)
    def test_blind_worlds_have_identical_public_input_and_full_search_choice(self):
        u=self.u;initial=u.setup(390000001)
        worlds=[];observations=[]
        for seed in range(101,111):
            s,seat=u.apply(initial,0,24,seed,deterministic=True)
            t=Tracker(u,initial);t.update(initial,s,0,24)
            worlds.append(s);observations.append(t.snapshot(s,seat))
        self.assertTrue(any(not u.np.array_equal(worlds[0],s) for s in worlds[1:]))
        self.assertTrue(all(observations[0]==o for o in observations))
        outputs=[];samples=[]
        for o in observations[:2]:
            self.reset();outputs.append(self.rpc.call(op='choose',observation=o,legal=u.legal(worlds[0],1)))
            samples.append(self.rpc.call(op='sample',observation=o,seed=1234))
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(samples[0],samples[1])
        self.assertEqual(samples[0]['observation'],observations[0])
    def test_hidden_fields_and_opponent_blind_ids_are_rejected(self):
        u=self.u;s=u.setup(390000002);t=Tracker(u,s)
        nxt,seat=u.apply(s,0,24,101,deterministic=True);t.update(s,nxt,0,24)
        o=t.snapshot(nxt,seat);legal=u.legal(nxt,seat)
        self.reset()
        for key in ['setup_seed','decks','rng','sampled_hidden_world']:
            bad=copy.deepcopy(o);bad[key]=42
            with self.assertRaises(RuntimeError):self.rpc.call(op='choose',observation=bad,legal=legal)
        bad=copy.deepcopy(o);bad['players'][0]['reserved'][0]['card']=t.snapshot(nxt,seat,full=True)['players'][0]['reserved'][0]['card']
        with self.assertRaises(RuntimeError):self.rpc.call(op='choose',observation=bad,legal=legal)
    def test_legal_actions_do_not_depend_on_unknown_private_card_assignment(self):
        u=self.u;s=u.setup(390000003);t=Tracker(u,s)
        nxt,seat=u.apply(s,0,24,101,deterministic=True);t.update(s,nxt,0,24)
        o=t.snapshot(nxt,seat);self.reset()
        legal=u.legal(nxt,seat)
        self.rpc.call(op='choose',observation=o,legal=legal)
        with self.assertRaises(RuntimeError):self.rpc.call(op='choose',observation=o,legal=legal[:-1])
    def test_same_champion_bytes_and_pinned_source(self):
        self.assertEqual(sha(ROOT/'research/e56/model/model.bin'),'055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41')

if __name__=='__main__':unittest.main()
