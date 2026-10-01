import sys,json,torch,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from residual_model import Residual,export
from flywheel_model import bootstrap,raw,open_rows,sha
out=ROOT/'research/e77';torch.manual_seed(800000015);torch.set_num_threads(4)
m=Residual(ROOT/'research/e68/model/model.pt',384,6).eval();b=bootstrap(ROOT/'research/e68/model/model.pt').eval()
r,_,_=open_rows([ROOT/'local/research/e74/dev.bin']);x=torch.from_numpy(np.array(r[0]['x'][:64]))
a=m(x);z=raw(b,x)
assert all(torch.equal(v,w) for v,w in zip(a,z))
loss=a[0].square().mean()+a[1].square().mean();loss.backward()
assert m.delta.head.weight.grad.abs().sum()>0
assert all(p.grad is None for p in m.base.parameters())
export(m,out/'initial.bin');torch.save(dict(state_dict=m.state_dict(),architecture='residual',**m.metadata()),out/'initial.pt')
n=Residual(out/'initial.pt').eval();assert all(torch.equal(v,w) for v,w in zip(m(x),n(x)))
# Native parity fixture follows the existing transfer_parity format.
print(json.dumps(dict(parameters=sum(p.numel() for p in m.parameters()),trainable_parameters=sum(p.numel() for p in m.parameters() if p.requires_grad),initial_exact=True,frozen_base=True,gradient_head_l1=float(m.delta.head.weight.grad.abs().sum()),reload_exact=True,native_sha256=sha(out/'initial.bin'))))

with torch.no_grad():
 pi,v=m(x)
(out/"parity.json").write_text(json.dumps(dict(x=x.tolist(),logits=pi.tolist(),values=v.tolist())))
