"""Check initialization, context separation, gradients and native fixture."""
import sys,json,copy
from pathlib import Path
sys.path.insert(0,str(Path('research').resolve()))
import numpy as np
import torch
from flywheel_model import bootstrap,expand_inputs,raw,export,DTYPE,sha
OUT=Path('research/e70');torch.set_num_threads(4);torch.manual_seed(800000013)
r=np.memmap('local/research/e68/dev.bin',mode='r',dtype=DTYPE);c=np.memmap('local/research/e68/dev.context.bin',mode='r',dtype='<f4',shape=(len(r),7))
indices=np.linspace(0,len(r)-1,64,dtype=int);x=np.array(r['x'][indices],copy=True);context=np.array(c[indices],copy=True);y=np.concatenate([x,context],axis=-1)
base=bootstrap('research/e59/model/model.pt').eval();model=expand_inputs(copy.deepcopy(base),57).eval()
with torch.no_grad():a=raw(base,torch.from_numpy(x));b=raw(model,torch.from_numpy(y))
errors=[float((u-v).abs().max()) for u,v in zip(a,b)];assert max(errors)<1e-5
export(model,OUT/'zero.bin')
(OUT/'zero-parity.json').write_text(json.dumps(dict(x=x.tolist(),context=context.tolist(),logits=b[0].tolist(),values=b[1].tolist())))
saved=dict(state_dict=model.state_dict(),input_rows=57,architecture='bootstrap',trunk_blocks=1);torch.save(saved,OUT/'zero.pt')
reload=bootstrap(OUT/'zero.pt').eval()
with torch.no_grad():assert all(torch.equal(u,v) for u,v in zip(raw(model,torch.from_numpy(y)),raw(reload,torch.from_numpy(y))))
model.train();mask=torch.from_numpy(np.array(r['mask'][indices],copy=True));target=torch.from_numpy(np.array(r['policy'][indices],copy=True));pi,v=raw(model,torch.from_numpy(y));loss=-(target*pi.masked_fill(mask==0,-1e9).log_softmax(-1)).sum(-1).mean();loss.backward();assert model.first_layer.linear.weight.grad[:,-1].abs().sum()>0
result=dict(parameters=sum(p.numel() for p in model.parameters()),extra_parameters=56,initial_python_max_errors=errors,checkpoint_reload_exact=True,context_gradient_nonzero=True,model_sha256=sha(OUT/'zero.bin'),fixture_positions=64)
(OUT/'python-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
