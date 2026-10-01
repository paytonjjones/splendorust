"""Verify zero identity, frozen-base updates, reload, and native fixtures."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('research').resolve()))
import numpy as np
import torch
from residual_model import Residual,export
from flywheel_model import bootstrap,raw,DTYPE,sha
OUT=Path('research/e62');torch.manual_seed(800000011);torch.set_num_threads(4)
r=np.memmap('local/research/e58/dev.bin',dtype=DTYPE,mode='r');b=np.array(r[np.linspace(0,len(r)-1,64,dtype=int)],copy=True)
x=torch.from_numpy(b['x']);mask=torch.from_numpy(b['mask']);target=torch.from_numpy(b['policy'])
m=Residual('research/e59/model/model.pt').eval();base=bootstrap('research/e59/model/model.pt').eval()
assert all(torch.equal(a,b) for a,b in zip(m(x),raw(base,x)))
frozen={k:v.clone() for k,v in m.base.state_dict().items()}
def fixture(name):
 p=OUT/name;p.mkdir(exist_ok=True);export(m,p/'model.bin')
 assert sha(p/'base.bin')==sha('research/e59/model/model.bin')
 with torch.no_grad():pi,v=m.eval()(x)
 (p/'parity.json').write_text(json.dumps(dict(x=x.tolist(),logits=pi.tolist(),values=v.tolist())))
fixture('zero')
m.train();assert not any(v.training for v in m.base.modules())
opt=torch.optim.AdamW([p for p in m.parameters() if p.requires_grad],lr=1e-4)
for _ in range(3):
 opt.zero_grad();pi,v=m(x);loss=-(target*pi.masked_fill(mask==0,-1e9).log_softmax(-1)).sum(-1).mean()+v.square().mean();loss.backward()
 assert m.delta.head.weight.grad.abs().sum()>0
 assert all(p.grad is None for p in m.base.parameters())
 opt.step()
assert all(torch.equal(v,m.base.state_dict()[k]) for k,v in frozen.items())
assert not torch.equal(m.eval()(x)[0],raw(base,x)[0])
fixture('updated')
p=OUT/'updated/model.pt';torch.save(dict(architecture='residual',state_dict=m.state_dict(),**m.metadata()),p)
reloaded=Residual(p).eval();assert all(torch.equal(a,b) for a,b in zip(m(x),reloaded(x)))
(OUT/'python-checks.json').write_text(json.dumps(dict(positions=64,initial_identity_exact=True,frozen_base_exact=True,base_export_exact=True,checkpoint_reload_exact=True,trainable_parameters=sum(p.numel() for p in m.parameters() if p.requires_grad),parameters=sum(p.numel() for p in m.parameters())),indent=2)+'\n')
print((OUT/'python-checks.json').read_text())
