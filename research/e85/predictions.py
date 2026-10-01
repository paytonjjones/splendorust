"""Network sensitivity on the fixed sampled-world diagnostic; all81 outputs."""
import json,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import bootstrap,raw,sha
torch.set_num_threads(4)
rows=[json.loads(s) for s in (ROOT/'local/research/e85/moments.jsonl').open()]
x=torch.tensor(np.array([r['x'] for r in rows],dtype=np.float32));mean=torch.tensor(np.array([r['mean'] for r in rows],dtype=np.float32))
model=bootstrap(ROOT/'research/e81/model/model.pt').eval()
with torch.no_grad():
 old,v=raw(model,x);new,w=raw(model,mean);old=old.softmax(-1).numpy();new=new.softmax(-1).numpy();v=v.numpy();w=w.numpy()
metrics={}
for label,blind in [('no_blind',False),('blind',True)]:
 tv=[];variation=[];mean_tv=[];mean_variation=[];shift=[]
 for start in range(0,len(rows),8):
  if bool(rows[start]['context'][6])!=blind:continue
  a=slice(start,start+8)
  tv.extend((np.abs(old[a]-old[start]).sum(-1)/2).tolist());variation.extend(np.max(np.abs(v[a]-v[start]),axis=-1).tolist())
  mean_tv.extend((np.abs(new[a]-new[start]).sum(-1)/2).tolist());mean_variation.extend(np.max(np.abs(w[a]-w[start]),axis=-1).tolist())
  shift.extend((np.abs(new[a]-old[a]).sum(-1)/2).tolist())
 metrics[label]=dict(observations=len(tv)//8,raw_mean_policy_tv=float(np.mean(tv)),raw_max_policy_tv=float(np.max(tv)),raw_max_value_variation=float(np.max(variation)),mean_input_max_policy_tv=float(np.max(mean_tv)),mean_input_max_value_variation=float(np.max(mean_variation)),mean_input_shift_tv=float(np.mean(shift)))
print(json.dumps(dict(model_sha256=sha(ROOT/'research/e81/model/model.bin'),scope='unmasked native81-output distributions; diagnostic only, not full search',metrics=metrics),indent=2))
