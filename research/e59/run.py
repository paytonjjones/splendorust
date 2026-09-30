"""Convergence control with the same full-volume teacher corpus."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e59';LOCAL=ROOT/'local/research/e58';LOCAL.mkdir(exist_ok=True)
BIN=ROOT/'local/research/flywheel-target/release';CHAMPION=ROOT/'research/e56/model'
EXPECTED='055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41'
scripts={p:sha(ROOT/'research'/p) for p in ['train_flywheel.py','flywheel_model.py','encoding_views.py','lineage.py']}
plan=dict(schema='lineage-generation-v1',train_seed=3510000000,dev_seed=3520000000,screen_seed=3540000000,train_games=5000,dev_games=1000,training_seed=800000009,epochs=50,teacher_iterations=800,screen_iterations=128,threads=14,champion_sha256=EXPECTED,script_sha256=sha(__file__),training_scripts_sha256=scripts,rule='provisional worst-case requested point >50.5%; final strict champion gate',replay='E56 recent1000-game train shard',augmentation=False,wait_for='E58 selected endpoint')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
queued=time.monotonic()
while not (ROOT/'research/e58/completed.json').exists():
 if time.monotonic()-queued>7200:raise RuntimeError('E58 incomplete; retain all evidence')
 time.sleep(10)
start=time.monotonic()
for name,h in scripts.items():assert sha(ROOT/'research'/name)==h
assert sha(CHAMPION/'model.bin')==EXPECTED
warm=dict(model=str(CHAMPION/'model.bin'),checkpoint=str(CHAMPION/'model.pt'),model_sha256=EXPECTED,checkpoint_sha256=sha(CHAMPION/'model.pt'))
parent=json.loads((ROOT/'research/e58/endpoint.json').read_text());assert sha(parent['model'])==parent['model_sha256']
(OUT/'parent.json').write_text(json.dumps(parent,indent=2)+'\n')
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),SPLENDOR_BEST_MODEL=parent['model'],CARGO_BUILD_JOBS='2')
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit{r.returncode}')
replay=[ROOT/'local/research/e56/train.bin']
for split in ['train','dev']:
 receipt=json.loads((ROOT/'research/e58'/(split+'-hashes.json')).read_text());assert sha(LOCAL/(split+'.bin'))==receipt['data_sha256']
for name in scripts:shutil.copy2(ROOT/'research'/name,OUT/name)
command=[sys.executable,ROOT/'research/train_flywheel.py','--train',*replay,LOCAL/'train.bin','--dev',LOCAL/'dev.bin','--output',OUT/'model','--warmstart',warm['checkpoint'],'--epochs',50,'--batch-size',1024,'--device','mps','--seed',800000009,'--selection','outcome','--learning-rate',0.0001]
run(command,'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
assert sha(OUT/'model/model.bin')==m['model_sha256']
endpoint=parent
if m['model_sha256']==parent['model_sha256']:
 result=dict(selected=False,reason='unchanged parent function; skip self-comparison')
else:
 env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin')
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',3540000000,'--output',OUT/'gate'],'gate.log',(0,2))
 report=json.loads((OUT/'gate/screen.json').read_text());assert report['seed']==3540000000 and report['requested_games']==2000
 result=provisional_decision(report);result['strict_decision']=json.loads((OUT/'gate/decision.json').read_text())
 if result['selected']:endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage; final champion assessment pending')
result.update(parent_sha256=parent['model_sha256'],candidate_sha256=m['model_sha256'],champion_sha256=EXPECTED,augmentation=False)
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
assert sha(CHAMPION/'model.bin')==EXPECTED
run([sys.executable,ROOT/'research/distillation_fit.py','--train',LOCAL/'train.bin','--dev',LOCAL/'dev.bin','--checkpoint',OUT/'model/model.pt','--output',OUT/'fit-diagnostic.json'],'fit.log')
(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,decision=result,seconds=time.monotonic()-start),indent=2)+'\n')
print(json.dumps(result),flush=True)
