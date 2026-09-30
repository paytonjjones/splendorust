"""E51 target semantics: opening, boundary, ties, legal support, immutability."""
import sys
from pathlib import Path
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train_flywheel import greedy_visit_targets
x=torch.zeros(4,392);x[:,6]=torch.tensor([5.,6.,40.,124.])
p=torch.tensor([[.1,.4,.4,.1],[.1,.4,.4,.1],[0.,1.,0.,0.],[.1,.2,.3,.4]])
original=p.clone();q=greedy_visit_targets(x,p)
assert torch.equal(q[0],p[0])
assert torch.equal(q[1],torch.tensor([0.,.5,.5,0.]))
assert torch.equal(q[2],p[2])
assert torch.equal(q[3],torch.tensor([0.,0.,0.,1.]))
assert torch.equal(q.sum(-1),torch.ones(4))
assert not ((p==0)&(q!=0)).any()
assert torch.equal(p,original)
print('Target semantics pass')
