"""Measure noise on genuine teacher observations; sample one row per blind game."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flywheel_model import bootstrap,raw,open_rows,sha
from encoding_views import open_views
root=Path('local/research/e54/flywheel/cycle-000/train');paths=[str(root/'000000.bin')]
base,_,_=open_rows(paths);groups,files=open_views(paths,base);b=base[0];g=groups[0]
setup=b['setup'][g['row'].astype(np.int64)];rng=np.random.default_rng(1360000007)
selected=[]
for identity in rng.permutation(np.unique(setup))[:512]:selected.append(rng.choice(np.flatnonzero(setup==identity)))
indices=np.array(selected);rows=g['row'][indices].astype(np.int64)
x=np.concatenate([np.array(b['x'][rows])[:,None,:],np.array(g['x'][indices])],axis=1)
model=bootstrap('research/e41/cycle-0/model/model.pt').eval();torch.set_num_threads(1)
outputs=[];values=[]
with torch.no_grad():
 for start in range(0,len(x),32):
  t=torch.from_numpy(x[start:start+32].reshape(-1,392).copy());l,v=raw(model,t)
  mask=torch.from_numpy(np.repeat(np.array(b['mask'][rows[start:start+32]]),8,axis=0))
  outputs.append(l.masked_fill(mask==0,-1e9).softmax(-1).numpy().reshape(-1,8,81));values.append(v[:,0].numpy().reshape(-1,8))
p=np.concatenate(outputs);v=np.concatenate(values);mean=p.mean(1,keepdims=True);tv=np.abs(p-mean).sum(2)/2
meta=json.loads((root/'000000.json').read_text())
r=dict(shard=str(root/'000000.bin'),data_sha256=sha(root/'000000.bin'),views_sha256=files[0]['sha256'],model_sha256=sha('research/e41/cycle-0/model/model.bin'),sampled_blind_games=len(indices),all_rows=len(b),blind_rows=len(g),blind_row_fraction=len(g)/len(b),mean_policy_tv=float(tv.mean()),p95_policy_tv=float(np.quantile(tv,.95)),argmax_disagreement=float((p.argmax(2)!=mean.argmax(2)).mean()),mean_value_std=float(v.std(1).mean()),mean_value_range=float(np.ptp(v,axis=1).mean()),max_value_range=float(np.ptp(v,axis=1).max()),note='One randomly selected blind observation per sampled game, first completed1000-game800-simulation shard; CPU Torch outputs. Not a final arena dataset.')
Path('research/e54/teacher-encoding-summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
