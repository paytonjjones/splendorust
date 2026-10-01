"""Initial public model, frozen base, zero correction and export checks."""
import json,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'research/e88'))
from flywheel_model import DTYPE,raw,sha
from attention_model import AttentionResidual as BeliefResidual,export
torch.set_num_threads(4);torch.manual_seed(800000020)
path=ROOT/'local/research/e88/data/e87-dev.bin';rows=np.memmap(path,mode='r',dtype=DTYPE);ctx=np.memmap(path.with_suffix('.context.bin'),mode='r',dtype='<f4',shape=(len(rows),911))
x=np.array(rows['x'][:64],copy=True);c=np.array(ctx[:64],copy=True);z=torch.from_numpy(np.concatenate([x,c],axis=1))
model=BeliefResidual(ROOT/'research/e81/model/model.pt').eval()
with torch.no_grad():
 pi,v=model(z);bpi,bv=raw(model.base,z[:,392:784]);assert torch.equal(pi,bpi) and torch.equal(v,bv)
model.train();model(z)[0].square().mean().backward();assert model.delta.head.weight.grad.abs().sum()>0
assert all(p.grad is None for p in model.base.parameters())
model.eval();out=ROOT/'research/e88/initial';out.mkdir(exist_ok=True);export(model,out/'model.bin')
assert sha(out/'base.bin')==sha(ROOT/'research/e81/model/model.bin')
(out/'parity.json').write_text(json.dumps(dict(x=x.tolist(),context=c[:,-7:].tolist(),logits=pi.detach().tolist(),values=v.detach().tolist())))
(ROOT/'research/e88/python-checks.json').write_text(json.dumps(dict(zero_correction_exact=True,frozen_base_sha256=sha(out/'base.bin'),head_gradient_nonzero=True,base_gradients_absent=True,parameters=sum(p.numel() for p in model.parameters()),trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad)),indent=2)+'\n')

with torch.no_grad():
 model.delta.head.weight.normal_(0,.01);model.delta.head.bias.normal_(0,.01)
 pi,v=model(z)
export(model,out/'probe.bin')
(out/'probe-parity.json').write_text(json.dumps(dict(x=x.tolist(),context=c[:,-7:].tolist(),logits=pi.tolist(),values=v.tolist())))
