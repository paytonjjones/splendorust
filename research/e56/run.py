"""Third preregistered lineage generation and independent fixed-champion test."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e56';LOCAL=ROOT/'local/research/e56';LOCAL.mkdir(exist_ok=True)
BIN=ROOT/'local/research/flywheel-target/release';CHAMPION=ROOT/'research/e41/cycle-0/model'
EXPECTED='d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600'
scripts={p:sha(ROOT/'research'/p) for p in ['train_flywheel.py','flywheel_model.py','encoding_views.py','lineage.py']}
plan=dict(schema='lineage-generation-v1',train_seed=1390000000,dev_seed=1400000000,screen_seed=1410000000,milestone_seed=3310000000,milestone_games=20000,training_seed=800000008,epochs=10,teacher_iterations=800,screen_iterations=128,threads=14,champion_sha256=EXPECTED,script_sha256=sha(__file__),training_scripts_sha256=scripts,rule='provisional worst-case requested point >50.5%; final strict champion gate',replay='E54 five original train shards',augmentation='only if E55 selected')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
start=time.monotonic()
while not (ROOT/'research/e55/completed.json').exists():
 if time.monotonic()-start>7200:raise RuntimeError('E55 did not finish; no dependent run')
 time.sleep(10)
for name,h in scripts.items():assert sha(ROOT/'research'/name)==h
assert sha(CHAMPION/'model.bin')==EXPECTED
parent=json.loads((ROOT/'research/e55/best.json').read_text());assert sha(parent['model'])==parent['model_sha256']
aug=json.loads((ROOT/'research/e55/decision.json').read_text())['selected']
(OUT/'parent.json').write_text(json.dumps(parent,indent=2)+'\n')
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),SPLENDOR_BEST_MODEL=parent['model'],CARGO_BUILD_JOBS='2')
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit{r.returncode}')
for split,seed in [('train',1390000000),('dev',1400000000)]:
 path=LOCAL/(split+'.bin')
 run([BIN/'examples/flywheel_data','--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',800,'--depth',16,'--threads',14,'--encoding-views',8,'--output',path],split+'.log')
 shutil.copy2(path.with_suffix('.json'),OUT/(split+'.json'))
 (OUT/(split+'-hashes.json')).write_text(json.dumps(dict(data_sha256=sha(path),views_sha256=sha(path.with_suffix('.views.bin')),teacher_sha256=parent['model_sha256']),indent=2)+'\n')
replay=sorted(p for p in (ROOT/'local/research/e54/flywheel/cycle-000/train').glob('*.bin') if not p.name.endswith('.views.bin'))
assert len(replay)==5
for name in scripts:shutil.copy2(ROOT/'research'/name,OUT/name)
command=[sys.executable,ROOT/'research/train_flywheel.py','--train',*replay,LOCAL/'train.bin','--dev',LOCAL/'dev.bin','--output',OUT/'model','--warmstart',parent['checkpoint'],'--epochs',10,'--batch-size',1024,'--device','mps','--seed',800000008,'--selection','outcome','--learning-rate',0.0001]
if aug:command+=['--sample-encoding-views']
run(command,'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
assert sha(OUT/'model/model.bin')==m['model_sha256']
endpoint=parent
if m['model_sha256']==parent['model_sha256']:
 result=dict(selected=False,reason='unchanged parent function; skip self-comparison')
else:
 env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin')
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',1410000000,'--output',OUT/'gate'],'gate.log',(0,2))
 report=json.loads((OUT/'gate/screen.json').read_text());assert report['seed']==1410000000 and report['requested_games']==2000
 result=provisional_decision(report);result['strict_decision']=json.loads((OUT/'gate/decision.json').read_text())
 if result['selected']:endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage; final champion assessment pending')
result.update(parent_sha256=parent['model_sha256'],candidate_sha256=m['model_sha256'],champion_sha256=EXPECTED,augmentation=aug)
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
# Endpoint is frozen before the independent milestone outcomes.
assert sha(endpoint['model'])==endpoint['model_sha256'] and sha(CHAMPION/'model.bin')==EXPECTED
if endpoint['model_sha256']==EXPECTED:
 milestone=dict(decision='no new endpoint; skip identical champion self-comparison',confirmed=False)
else:
 env['SPLENDOR_BEST_MODEL']=str(CHAMPION/'model.bin');env['SPLENDOR_CANDIDATE_MODEL']=endpoint['model']
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',20000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',3310000000,'--output',OUT/'milestone'],'milestone.log',(0,2))
 milestone=json.loads((OUT/'milestone/decision.json').read_text());milestone['confirmed']=milestone['decision']=='promote'
assert sha(CHAMPION/'model.bin')==EXPECTED and sha(endpoint['model'])==endpoint['model_sha256']
(OUT/'milestone-decision.json').write_text(json.dumps(milestone,indent=2)+'\n');(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,milestone=milestone,seconds=time.monotonic()-start),indent=2)+'\n')
print(json.dumps(dict(generation=result,milestone=milestone)),flush=True)
