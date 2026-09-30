#!/usr/bin/env python3
"""Check observation-only binary supervision before training."""
import argparse,json
import numpy as np
p=argparse.ArgumentParser();p.add_argument('file');p.add_argument('--expert',action='store_true');a=p.parse_args()
dtype=np.dtype([('setup','<u8'),('x','<f4',(322,)),('mask','<f4',(67,)),('policy','<f4',(67,)),('teacher','<f4'),('baseline','<f4'),('value','<f4')])
r=np.fromfile(a.file,dtype=dtype)
assert len(r)>0 and np.all(np.isfinite(r['x'])) and np.all(np.isfinite(r['baseline']))
assert np.all((r['mask']==0)|(r['mask']==1)) and np.all(r['mask'].sum(-1)>0)
assert np.all(np.isfinite(r['policy'])) and np.all(r['policy']>=0)
assert np.all(r['policy'][r['mask']==0]==0)
sums=r['policy'].sum(-1)
assert np.all(np.isclose(sums,1,atol=1e-5)|(a.expert & np.isclose(sums,0)))
for key in ('teacher','value'):
    v=r[key];assert np.all(np.isnan(v)|((v>=0)&(v<=1)))
if a.expert:assert np.all(np.isnan(r['teacher']))
print(json.dumps({'rows':len(r),'setups':len(set(r['setup'])),'policy_rows':int((sums>0).sum()),'outcome_rows':int(np.isfinite(r['value']).sum()),'teacher_rows':int(np.isfinite(r['teacher']).sum()),'checks':'finite features, legal masks, normalized policies, bounded/masked values'}))
