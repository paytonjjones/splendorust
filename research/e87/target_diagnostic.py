"""Descriptive teacher-value calibration; never an arena-selection rule."""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
result={}
for name,p in [('weak_actor',ROOT/'local/research/e82/train/000000.bin'),('strong_actor',ROOT/'local/research/e87/train/000000.bin')]:
 r=np.memmap(p,mode='r',dtype=DTYPE);valid=np.isfinite(r['teacher'])&np.isfinite(r['outcome']);t=r['teacher'][valid].astype(np.float64);o=r['outcome'][valid].astype(np.float64);turn=r['x'][valid,6]
 groups={}
 for label,mask in [('all',np.ones(len(t),dtype=bool)),('early',turn<20),('middle',(turn>=20)&(turn<40)),('late',turn>=40)]:
  groups[label]=dict(rows=int(mask.sum()),teacher_outcome_brier=float(np.mean((t[mask]-o[mask])**2)),teacher_mean=float(np.mean(t[mask])),outcome_mean=float(np.mean(o[mask])))
 result[name]=dict(data_sha256=sha(p),groups=groups)
result['scope']='Different trajectories and RNG; descriptive calibration only, no causal conclusion or promotion'
(ROOT/'research/e87/target-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
