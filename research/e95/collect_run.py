"""Validate parallel corpus identity, then collect disjoint external expert splits."""
import concurrent.futures,json,os,subprocess,sys,time,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'research/e95';LOCAL=ROOT/'local/research/e95';sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
PYTHON=ROOT/'local/strength/inference/bin/python';start=time.monotonic()
def shard(master,offset,games,dest):
 log=dest.with_suffix('.log')
 with log.open('w') as f:r=subprocess.run([str(PYTHON),str(OUT/'collect.py'),'--master',str(master),'--offset',str(offset),'--games',str(games),'--output',str(dest)],stdout=f,stderr=subprocess.STDOUT)
 assert r.returncode==0,f'{log}: exit {r.returncode}'
 return json.loads((dest/'checks.json').read_text())
def stage(master,games,workers,name,size):
 directory=LOCAL/name;directory.mkdir(exist_ok=False);beg=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
  jobs=[pool.submit(shard,master,i,min(size,games-i),directory/f'{i:06}') for i in range(0,games,size)]
  receipts=[]
  for job in jobs:
   receipts.append(job.result());(OUT/'progress.json').write_text(json.dumps(dict(stage=name,completed_games=sum(r['games'] for r in receipts),seconds=time.monotonic()-start),indent=2)+'\n')
 result=dict(stage=name,games=games,workers=workers,shard_games=size,seconds=time.monotonic()-beg,receipts=receipts)
 (OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');return result
# Two independently initialized processes reproduce the serial pilot rows exactly.
r=stage(4869000000,2,2,'validation-parallel',1)
for name in ['data.bin','data.context.bin']:
 joined=b''.join((LOCAL/'validation-parallel'/f'{i:06}'/name).read_bytes() for i in range(2));assert joined==(LOCAL/'validation-serial'/name).read_bytes()
# Fixed 28-game workload above four workers. Native arrays and histories must match.
a=stage(4869001000,28,8,'scaling-8',2);b=stage(4869001000,28,14,'scaling-14',2)
for offset in range(0,28,2):
 for name in ['data.bin','data.context.bin']:
  assert sha(LOCAL/'scaling-8'/f'{offset:06}'/name)==sha(LOCAL/'scaling-14'/f'{offset:06}'/name)
 for name in ['histories.json.gz']:
  h=[json.loads(gzip.decompress((LOCAL/f'scaling-{w}'/f'{offset:06}'/name).read_bytes()))['games'] for w in [8,14]];assert h[0]==h[1]
workers=14 if b['seconds']<a['seconds'] else 8
(OUT/'scaling.json').write_text(json.dumps(dict(exact_data_and_replay_identity=True,seconds_8=a['seconds'],seconds_14=b['seconds'],selected_workers=workers,includes_startup=True,scope='Fixed 28-game collection pilot; shared host'),indent=2)+'\n')
plan=dict(schema='external-teacher-full-corpus-v1',train_games=5000,dev_games=1000,train_master=4840000000,dev_master=4850000000,workers=workers,shard_games=200,files={str(p):sha(p) for p in [OUT/'collect.py',Path(__file__),ROOT/'local/research/e92/frozen/native_policy_worker',ROOT/'research/e81/model/model.bin',ROOT/'benchmarks/strength/native/upstream.py',ROOT/'local/strength/external/alphazero/splendor/pretrained_2players.pt']})
assert not (OUT/'collection-plan.json').exists();(OUT/'collection-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for name,master,games in [('train',4840000000,5000),('dev',4850000000,1000)]:stage(master,games,workers,name,200)
assert all(sha(p)==h for p,h in plan['files'].items())
(OUT/'collection-complete.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,all_requested_games_completed_and_replayed=True),indent=2)+'\n')
