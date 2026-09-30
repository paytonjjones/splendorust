"""Check initial identity, critic isolation, optimizer step and checkpoint reload."""
import sys,tempfile
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from split_model import SplitBootstrap
from flywheel_model import bootstrap,raw,open_rows
warm='research/e41/cycle-0/model/model.pt'
m=SplitBootstrap(warm).eval();base=bootstrap(warm).eval()
rows,_,_=open_rows(['local/research/e43/dev800.bin'])
x=torch.from_numpy(np.array(rows[0]['x'][:64],copy=True))
with torch.no_grad():
 p,v=m(x);bp,bv=raw(base,x)
assert torch.equal(p,bp) and torch.equal(v,bv)
before={k:t.clone() for k,t in m.critic.state_dict().items()}
m.train();assert not m.critic.training and m.policy.trunk.training
assert not m.policy.output_layers_V.training
optimizer=torch.optim.AdamW([p for p in m.parameters() if p.requires_grad],lr=1e-4)
p,_=m(x);p.square().mean().backward();optimizer.step()
assert all(torch.equal(before[k],t) for k,t in m.critic.state_dict().items())
m.eval()
with torch.no_grad():p,v=m(x)
assert torch.equal(v,bv) and not torch.equal(p,bp)
with tempfile.TemporaryDirectory() as directory:
 checkpoint=Path(directory)/'model.pt'
 torch.save(dict(architecture='split-bootstrap',policy_trunk_blocks=1,critic_trunk_blocks=1,state_dict=m.state_dict()),checkpoint)
 loaded=SplitBootstrap(checkpoint).eval()
 with torch.no_grad():lp,lv=loaded(x)
 assert torch.equal(lp,p) and torch.equal(lv,v)
print('Initial identity, isolated optimizer step, fixed state/value and checkpoint reload pass')
