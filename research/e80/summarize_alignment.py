import json,statistics,hashlib
from pathlib import Path
p=Path('research/e80/alignment.jsonl');rows=[json.loads(s) for s in p.read_text().splitlines()];result={}
for stress in [False,True]:
 for name in ['flywheel-gumbel','flywheel-gumbel-noisy']:
  group=[r for r in rows if r['stress']==stress and r['teacher']==name];result[f'{name}-stress{stress}']=dict(rows=len(group),observations=len({(r['game'],r['turn']) for r in group}),selected_argmax_agreement=sum(r['selected_index']==r['argmax_index'] for r in group)/len(group),mean_selected_probability=statistics.mean(r['selected_probability'] for r in group),median_selected_probability=statistics.median(r['selected_probability'] for r in group))
result['scope']='Fixed ordinary/forced-blind Strong trajectories, four independent teachers per observation; conditional diagnostic, not corpus prevalence or playing strength';result['raw_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();Path('research/e80/alignment-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
