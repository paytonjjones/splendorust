#!/usr/bin/env python3
"""Deterministic full-batch logistic regression, grouped independent seed files."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
import argparse, hashlib, json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
p.add_argument('train'); p.add_argument('dev'); p.add_argument('output')
a=p.parse_args()
def load(path):
    rows=[json.loads(s) for s in Path(path).read_text().splitlines()]
    return np.array([r['x'] for r in rows]),np.array([r['y'] for r in rows]),{r['setup'] for r in rows}
x,y,seeds=load(a.train); dx,dy,ds=load(a.dev)
assert not seeds & ds
# Pair differences have no intercept. Swapping player labels negates the logit.
w=np.zeros(x.shape[1]); ridge=0.0001
for step in range(80):
    z=np.clip(x@w,-30,30); q=1/(1+np.exp(-z))
    grad=x.T@(q-y)/len(y)+ridge*w
    hess=(x.T*(q*(1-q)))@x/len(y)+ridge*np.eye(len(w))
    change=np.linalg.solve(hess,grad)
    w-=change
    if np.max(np.abs(change)) < 1e-9: break
q=1/(1+np.exp(-np.clip(dx@w,-30,30)))
result={'architecture':'32-feature logistic, no intercept','weights':w.tolist(),'ridge':ridge,'steps':step+1,'train_rows':len(y),'dev_rows':len(dy),'train_setups':len(seeds),'dev_setups':len(ds),'dev_brier':float(np.mean((q-dy)**2)),'dev_logloss':float(-np.mean(dy*np.log(q)+(1-dy)*np.log(1-q))),'numpy':np.__version__,'train_sha256':hashlib.sha256(Path(a.train).read_bytes()).hexdigest(),'dev_sha256':hashlib.sha256(Path(a.dev).read_bytes()).hexdigest()}
Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='weights'},indent=2))
