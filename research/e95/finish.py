"""Run the registered model train and screens after validated expert collection."""
import json,os,subprocess,sys,time,statistics,gzip,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);OUT=ROOT/'research/e95';LOCAL=ROOT/'local/research/e95';PYTHON=ROOT/'local/strength/inference/bin/python';BIN=ROOT/'local/research/flywheel-target/release';sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2',SPLENDOR_BEST_MODEL=str(ROOT/'research/e81/model/model.bin'));start=time.monotonic()
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as f:r=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
 assert r.returncode in allowed,f'{name}: exit {r.returncode}'
while not (OUT/'collection-complete.json').exists():
 if (LOCAL/'collection-failed.json').exists():raise RuntimeError('collection failed; preserve records and diagnose')
 time.sleep(20)
plan=dict(schema='public-external-teacher-model-screen-v1',training_seed=800000022,epochs=10,batch_size=1024,learning_rate=1e-4,cost_limit=1.20,canonical_screen_master=4870000000,native_screen_master=4860000000,games_per_screen=2000,iterations=128,depth=16,canonical_threads=14,native_workers=8,collection_plan_sha256=sha(OUT/'collection-plan.json'),scripts={str(p):sha(p) for p in [Path(__file__),OUT/'train.py',OUT/'public_model.py',OUT/'cost.rs',ROOT/'research/e86/public_features.py']},champion_sha256=sha(ROOT/'research/e81/model/model.bin'))
assert not (OUT/'model-plan.json').exists();(OUT/'model-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
# Preserve compressed replay streams and per-shard checks; raw arrays stay local.
receipts=[]
for split in ['train','dev']:
 dest=OUT/'data'/split;dest.mkdir(exist_ok=False,parents=True)
 for shard in sorted((LOCAL/split).iterdir()):
  if not shard.is_dir():continue
  import shutil
  for name in ['plan.json','checks.json','histories.json.gz']:shutil.copy2(shard/name,dest/(shard.name+'-'+name))
  receipts.append(dict(split=split,shard=shard.name,data_sha256=sha(shard/'data.bin'),context_sha256=sha(shard/'data.context.bin'),histories_sha256=sha(shard/'histories.json.gz')))
(OUT/'data-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
run([PYTHON,OUT/'train.py','--output',OUT/'model','--epochs',10],'training.log')
model=OUT/'model/model.bin';manifest=json.loads((OUT/'model/manifest.json').read_text());assert sha(model)==manifest['model_sha256']
run([BIN/'examples/transfer_parity',model,OUT/'model/parity.json','real'],'trained-native-parity.log')
env['SPLENDOR_CANDIDATE_MODEL']=str(model)
run([LOCAL/'cost'],'cost.jsonl')
rows=[json.loads(s) for s in (OUT/'cost.jsonl').read_text().splitlines()];ratios=[]
for i in range(3):
 a=next(r for r in rows if r['repeat']==i and 'candidate' in r['agent']);b=next(r for r in rows if r['repeat']==i and 'candidate' not in r['agent']);assert a['simulations']==b['simulations'];ratios.append(a['seconds']/b['seconds'])
cost=dict(ratios=ratios,median_ratio=statistics.median(ratios),limit=1.20,passes=statistics.median(ratios)<=1.20,shared_host=True);(OUT/'cost-summary.json').write_text(json.dumps(cost,indent=2)+'\n')
# Keep diagnostic strength evidence if cost fails; selection then remains deferred.
run([PYTHON,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate','--baseline','flywheel-gumbel','--screen',2000,'--confirm',0,'--seed',4870000000,'--threads',14,'--iterations',128,'--depth',16,'--output',OUT/'canonical-gate'],'canonical-gate.log',(0,2))
decision=provisional_decision(json.loads((OUT/'canonical-gate/screen.json').read_text()));decision['strict_decision']=json.loads((OUT/'canonical-gate/decision.json').read_text());decision['champion_unchanged']=True;decision['cost_passes']=cost['passes'];
if not cost['passes']:decision.update(selected=False,reason='Decision cost exceeds cap; fixed-budget evidence only; cost-matched selection deferred')
(OUT/'canonical-decision.json').write_text(json.dumps(decision,indent=2)+'\n')
# Freeze actual post-check worker hashes, unlike E92's pre-build manifest.
workers=[ROOT/'target/release/examples'/n for n in ['native_policy_worker','native_rules_probe','strength_worker']]
paths=[model,*workers,ROOT/'benchmarks/strength/native/schedule.py',ROOT/'benchmarks/strength/native/run.py',ROOT/'benchmarks/strength/native/upstream.py',ROOT/'local/strength/external/alphazero/splendor/pretrained_2players.pt']
frozen={str(p):sha(p) for p in paths};(OUT/'native-plan.json').write_text(json.dumps(dict(master=4860000000,games=2000,iterations=128,search='gumbel',root_only=False,files=frozen,profile='alphazero-native-32a27ac-v1',scope='Public learner versus unchanged native-private AlphaZero800; separate from canonical screen'),indent=2)+'\n')
run([PYTHON,ROOT/'benchmarks/strength/native/schedule.py','--games',2000,'--master',4860000000,'--workers',8,'--iterations',128,'--search','gumbel','--model',model,'--output',OUT/'native-arena'],'native-schedule.log')
run([PYTHON,ROOT/'benchmarks/strength/native/replay.py',OUT/'native-arena/games.jsonl','--output',OUT/'native-replay.json'],'native-replay.log')
run([PYTHON,ROOT/'benchmarks/strength/native/summarize.py',OUT/'native-arena/games.jsonl','--output',OUT/'native-summary.json'],'native-summary.log')
assert all(sha(p)==h for p,h in frozen.items()) and all(sha(p)==h for p,h in plan['scripts'].items())
archives=[]
for path in sorted((OUT/'native-arena').glob('*.jsonl')):
 dest=path.with_suffix('.jsonl.gz')
 with dest.open('wb') as raw:
  with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz:
   with path.open('rb') as source:
    for chunk in iter(lambda:source.read(1<<20),b''):gz.write(chunk)
 assert hashlib.sha256(gzip.decompress(dest.read_bytes())).hexdigest()==sha(path);archives.append(dict(raw=str(path),raw_sha256=sha(path),archive_sha256=sha(dest)))
(OUT/'native-archives.json').write_text(json.dumps(archives,indent=2)+'\n')
(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,canonical_decision=decision,model_sha256=sha(model),champion_unchanged=True,native_summary=str(OUT/'native-summary.json')),indent=2)+'\n')
