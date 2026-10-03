import hashlib,json,os,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent
root=p.parents[2]
env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(root/'research/architecture_pivots/entity/model.bin'),SPLENDOR_BEST_MODEL=str(root/'research/e81/model/model.bin'))
results=[]
for iterations,games,master in [(0,128,5200000000),(128,32,5200010000)]:
 for workers in (14,32):
  name=f'g{iterations}-w{workers}';f=p/f'{name}.json'
  command=[str(p/'splendor.bin'),'compare','--agent-a','flywheel-gumbel-candidate','--agent-b','flywheel-gumbel','--games',str(games),'--players','2','--seed',str(master),'--threads',str(workers),'--iterations',str(iterations),'--depth','16','--output',str(f)]
  with (p/f'{name}.log').open('w') as log:subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  d=json.loads(f.read_text());records=json.dumps(d['records'],sort_keys=True,separators=(',',':')).encode()
  results.append(dict(iterations=iterations,workers=workers,completed=d['completed_games'],incomplete=d['incomplete_games'],seconds=d['runtime_seconds'],record_sha256=hashlib.sha256(records).hexdigest(),source_id=d['source_id']))
  (p/'progress.json').write_text(json.dumps(results,indent=2)+'\n')
checks=[]
for it in (0,128):
 a,b=[r for r in results if r['iterations']==it]
 checks.append(dict(iterations=it,ordered_records_equal=a['record_sha256']==b['record_sha256'],speed_ratio=a['seconds']/b['seconds']))
(p/'complete.json').write_text(json.dumps(dict(results=results,checks=checks,binary_sha256=hashlib.sha256((p/'splendor.bin').read_bytes()).hexdigest(),shared_host=True),indent=2)+'\n')
assert all(c['ordered_records_equal'] for c in checks)
