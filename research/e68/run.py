"""Comparable-volume strong-teacher labels on student-visited states."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e68';LOCAL=ROOT/'local/research/e68';BIN=ROOT/'local/research/flywheel-target/release';BASE=ROOT/'research/e59/model';CHAMPION=ROOT/'research/e56/model'
EXPECTED='76d45006d332dcd80635150f23917c321245f49cfb10a8e77654d3096505a918';assert sha(BASE/'model.bin')==EXPECTED
scripts={p:sha(ROOT/'research'/p) for p in ['train_flywheel.py','flywheel_model.py','lineage.py','encoding_views.py']};collector=ROOT/'crates/splendor-arena/examples/flywheel_data.rs'
plan=dict(schema='student-state-distillation-v1',train_seed=4210000000,dev_seed=4220000000,screen_seed=4230000000,train_games=5000,dev_games=1000,shard_games=1000,actor_iterations=128,teacher_iterations=800,teacher_replicates=1,screen_iterations=128,training_seed=800000013,epochs=10,batch_size=1024,learning_rate=1e-4,threads=14,base_sha256=EXPECTED,base_checkpoint_sha256=sha(BASE/'model.pt'),champion_sha256=sha(CHAMPION/'model.bin'),replay=dict(path=str(ROOT/'local/research/e64/train.bin'),sha256=sha(ROOT/'local/research/e64/train.bin')),collector_code_sha256=sha(collector),script_sha256=sha(__file__),training_scripts_sha256=scripts,rule='provisional worst-case requested point >50.5%; strict decisions preserved; no champion change')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');shutil.copy2(collector,OUT/'flywheel_data.rs')
for name in scripts:shutil.copy2(ROOT/'research'/name,OUT/name)
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),SPLENDOR_BEST_MODEL=str(BASE/'model.bin'),CARGO_BUILD_JOBS='2');start=time.monotonic()
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit {r.returncode}')
train=[]
for offset in range(0,5000,1000):
 path=LOCAL/'train'/f'{offset:06}.bin';seed=4210000000+offset
 run([BIN/'examples/flywheel_data','--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',800,'--actor-iterations',128,'--depth',16,'--threads',14,'--output',path],f'train-{offset:06}.log')
 shutil.copy2(path.with_suffix('.json'),OUT/f'train-{offset:06}.json')
 (OUT/f'train-{offset:06}-hashes.json').write_text(json.dumps(dict(data_sha256=sha(path),teacher_sha256=EXPECTED,collector_code_sha256=plan['collector_code_sha256']),indent=2)+'\n');train.append(path)
 (OUT/'progress.json').write_text(json.dumps(dict(stage='collection',completed_train_games=offset+1000,seconds=time.monotonic()-start),indent=2)+'\n')
path=LOCAL/'dev.bin';seed=4220000000
run([BIN/'examples/flywheel_data','--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',800,'--actor-iterations',128,'--depth',16,'--threads',14,'--output',path],'dev.log')
shutil.copy2(path.with_suffix('.json'),OUT/'dev.json');(OUT/'dev-hashes.json').write_text(json.dumps(dict(data_sha256=sha(path),teacher_sha256=EXPECTED),indent=2)+'\n')
assert sha(collector)==plan['collector_code_sha256'] and all(sha(ROOT/'research'/n)==h for n,h in scripts.items())
assert sha(plan['replay']['path'])==plan['replay']['sha256']
run([sys.executable,ROOT/'research/train_flywheel.py','--train',plan['replay']['path'],*train,'--dev',path,'--output',OUT/'model','--warmstart',BASE/'model.pt','--epochs',10,'--batch-size',1024,'--device','mps','--seed',800000013,'--selection','outcome','--learning-rate',0.0001],'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
endpoint=dict(model=str(BASE/'model.bin'),checkpoint=str(BASE/'model.pt'),model_sha256=EXPECTED,checkpoint_sha256=sha(BASE/'model.pt'))
if m['model_sha256']==EXPECTED:result=dict(selected=False,reason='unchanged initial endpoint; skip self-comparison')
else:
 env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin')
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',4230000000,'--output',OUT/'gate'],'gate.log',(0,2))
 report=json.loads((OUT/'gate/screen.json').read_text());assert report['seed']==4230000000 and report['requested_games']==2000
 result=provisional_decision(report);result['strict_decision']=json.loads((OUT/'gate/decision.json').read_text())
 if result['selected']:endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage only; milestone pending')
result.update(parent_sha256=EXPECTED,candidate_sha256=m['model_sha256'],champion_sha256=plan['champion_sha256'])
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
assert sha(CHAMPION/'model.bin')==plan['champion_sha256']
run([sys.executable,ROOT/'research/distillation_fit.py','--train',*train,'--dev',path,'--checkpoint',OUT/'model/model.pt','--output',OUT/'fit-diagnostic.json'],'fit.log')
(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,decision=result,seconds=time.monotonic()-start),indent=2)+'\n');print(json.dumps(result),flush=True)
