import json,hashlib,statistics
from pathlib import Path
import numpy as np
p=Path('research/e69/collisions.json');r=json.loads(p.read_text());rows=r['observations'];tvs=[];switch=[];value=[]
for row in rows:
 a,b=np.array(row['policies']);ma=a.mean(0);mb=b.mean(0);tvs.append(float(np.abs(ma-mb).sum()/2));switch.append(bool(ma.argmax()!=mb.argmax()))
 if all(v is not None for c in row['values'] for v in c):value.append(abs(statistics.mean(row['values'][0])-statistics.mean(row['values'][1])))
s=dict(observations=len(rows),all_input_collisions_exact=all(x['input_exact'] for x in rows),all_outputs_exact=all(x['outputs_exact'] for x in rows),mean_teacher_mean_policy_tv=statistics.mean(tvs),teacher_mean_argmax_switches=sum(switch),teacher_mean_argmax_switch_rate=statistics.mean(switch),mean_teacher_mean_value_difference=statistics.mean(value),raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='Exact information omission; finite eight-teacher contrasts on blind stress observations. Not a prevalence or playing-strength estimate.')
Path('research/e69/summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s))
