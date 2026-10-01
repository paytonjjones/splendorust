"""Excluded pilot: verify real gradient flow and export, not strength selection."""
import sys,json
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from flywheel_model import DTYPE,raw,sha
from public_model import load,inputs,export
out=ROOT/'local/research/e95/gradient-smoke';out.mkdir(exist_ok=False);torch.manual_seed(800000022);torch.set_num_threads(4)
r=np.fromfile(ROOT/'local/research/e95/validation-serial/data.bin',dtype=DTYPE);context=np.fromfile(ROOT/'local/research/e95/validation-serial/data.context.bin',dtype='<f4').reshape(-1,7);model=load(ROOT/'research/e81/model/model.pt').to('mps');optimizer=torch.optim.AdamW(model.parameters(),lr=1e-4,weight_decay=1e-4)
x=torch.from_numpy(inputs(r['x'],context,True)).to('mps');mask=torch.from_numpy(r['mask'].copy()).to('mps');target=torch.from_numpy(r['policy'].copy()).to('mps');vtarget=torch.from_numpy((r['teacher']+r['outcome']-1).copy()).to('mps');losses=[]
for step in range(4):
 pi,v=raw(model,x);logp=pi.masked_fill(mask==0,-1e9).log_softmax(-1);loss=-(target*logp).sum(-1).mean()+((v[:,0]-vtarget)**2+(v[:,1]+vtarget)**2).mean()/2
 assert torch.isfinite(loss);optimizer.zero_grad(set_to_none=True);loss.backward();assert torch.isfinite(model.first_layer.linear.weight.grad).all();assert model.first_layer.linear.weight.grad[:,56:].abs().sum()>0;torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step();losses.append(loss.item())
model.cpu().eval();assert model.first_layer.linear.weight[:,56:].abs().sum()>0;export(model,out/'model.bin');profiles=np.arange(len(r))%2
with torch.no_grad():pi,v=raw(model,torch.from_numpy(inputs(r['x'],context,profiles)))
(out/'parity.json').write_text(json.dumps(dict(x=r['x'].tolist(),context=context.tolist(),native_profiles=profiles.astype(bool).tolist(),logits=pi.tolist(),values=v.tolist()))+'\n')
(ROOT/'research/e95/gradient-smoke.json').write_text(json.dumps(dict(rows=len(r),mps_gradient_steps=4,losses=losses,extra_input_columns_have_finite_nonzero_gradients=True,model_sha256=sha(out/'model.bin'),training_eligible=False,scope='Excluded pipeline pilot only; no strength or checkpoint selection'),indent=2)+'\n')
