"""Architecture size, entity fields and legal history-boundary checks."""
import unittest
import numpy as np
import torch
from models import Capacity,EntityTransformer,entities,entities_fast
from history_data import prefix,event


class Models(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_major_capacity_and_outputs(self):
        for model in (Capacity(),EntityTransformer()):
            count=sum(p.numel() for p in model.parameters())
            self.assertTrue(2_000_000<count<7_000_000,count)
            x=torch.randn(2,525)
            pi,v=model.eval()(x)
            self.assertEqual(tuple(pi.shape),(2,81))
            self.assertEqual(tuple(v.shape),(2,2))
            self.assertTrue(torch.isfinite(pi).all())
            self.assertTrue((v.abs()<=1).all())
            (pi.sum()+v.sum()).backward()
            self.assertTrue(all(p.grad is not None for p in model.parameters()))

    def test_semantic_card_and_player_fields(self):
        x=torch.arange(525,dtype=torch.float32)[None]
        e=entities(x)
        self.assertTrue(torch.allclose(e[0,3,:14],x[0,7:21]/10))
        self.assertTrue(torch.allclose(e[0,1,:7],x[0,238:245]/10))
        self.assertEqual(e[0,0,7],x[0,519])
        self.assertTrue(torch.equal(e[0,24,7:47],x[0,392:432]))
        self.assertTrue(torch.equal(e[0,27,:7],x[0,512:519]))

    def test_vectorized_entity_encoding_is_exact(self):
        x=torch.randn(64,525)*100
        self.assertTrue(torch.equal(entities(x),entities_fast(x)))

    def test_prefix_excludes_future_and_limits_length(self):
        events=[np.zeros(32,dtype='<f4') for _ in range(20)]
        for i,e in enumerate(events):e[0]=1;e[1]=i%2;e[31]=i
        result=prefix(events,1)
        self.assertEqual(result[0,31],4)
        self.assertEqual(result[-1,31],19)
        self.assertEqual(result[-1,1],0)
        events[-1][31]=999
        self.assertEqual(result[-1,31],19)

    def test_blind_reservation_never_enters_public_event(self):
        before=dict(market=[255]*12,turns=2,players=[dict(tokens=[0]*6,owned=[])]*2)
        after=dict(players=[dict(tokens=[0,0,0,0,0,1],owned=[])]*2)
        e=event(before,after,24,0)
        self.assertTrue(np.all(e[10:24]==0))
        self.assertAlmostEqual(float(e[30]),1/3)

    def test_history_padding_and_auxiliary_outputs(self):
        model=EntityTransformer(history=True).eval()
        x=torch.zeros(2,525);h=torch.zeros(2,16,32)
        out=model(x,h)
        self.assertEqual(tuple(out[2].shape),(2,81))
        self.assertEqual(tuple(out[3].shape),(2,3,90))
        self.assertTrue(all(torch.isfinite(v).all() for v in out))

    def test_history_initialization_preserves_parent_and_belief_support(self):
        parent=EntityTransformer().eval();child=EntityTransformer(history=True).eval()
        child.load_state_dict(parent.state_dict(),strict=False)
        x=torch.randn(2,525);x[:,512:519]=0
        with torch.no_grad():
            old=parent(x);new=child(x)
        for a,b in zip(old,new[:2]):self.assertTrue(torch.allclose(a,b,atol=1e-5,rtol=1e-5))
        x.zero_();x[:,512]=1;x[:,515]=1/3
        pool=torch.zeros(2,90);pool[:,0]=1
        belief=child(x,pool=pool)[3].softmax(-1)
        self.assertTrue(torch.equal(belief[:,0,0],torch.ones(2)))
        self.assertTrue(torch.equal(belief[:,0,1:],torch.zeros(2,89)))


if __name__=='__main__':unittest.main()
