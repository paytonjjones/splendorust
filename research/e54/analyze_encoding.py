import json,numpy as np
from pathlib import Path
p=Path('local/research/e54/encoding-variance.json');r=json.loads(p.read_text());out=[]
for stress in [False,True]:
 for blind in [False,True]:
  group=[v for v in r['observations'] if v['stress']==stress and bool(v['opponent_blind'])==blind]
  if not group:continue
  policy=np.array([v['policy'] for v in group]);value=np.array([v['value'] for v in group])[:,:,0]
  mean=policy.mean(1,keepdims=True);tv=np.abs(policy-mean).sum(2)/2
  x=np.array([v['x'] for v in group]);changed=np.any(x!=x[:,:1],axis=(1,2))
  out.append(dict(stress=stress,opponent_blind=blind,observations=len(group),encoding_changed=float(changed.mean()),mean_policy_tv=float(tv.mean()),p95_policy_tv=float(np.quantile(tv,.95)),max_policy_tv=float(tv.max()),argmax_disagreement=float((policy.argmax(2)!=mean.argmax(2)).mean()),mean_value_std=float(value.std(1).mean()),mean_value_range=float(np.ptp(value,axis=1).mean()),max_value_range=float(np.ptp(value,axis=1).max())))
result=dict(source_id=r['source_id'],views=8,groups=out,cohorts=r['cohorts'],note='Strong and forced-blind stress cohorts; neither estimates neural teacher observation frequency.')
Path('research/e54/encoding-variance-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
