"""Paired full-volume teacher-label aggregation and frozen-lineage milestone."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha,DTYPE
from lineage import provisional_decision
OUT=ROOT/'research/e61';LOCAL=ROOT/'local/research/e61';LOCAL.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'local/research/flywheel-target/release';FIXED=ROOT/'research/e56/model'
EXPECTED='055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41'
SCRIPTS=['train_flywheel.py','flywheel_model.py','encoding_views.py','lineage.py','distillation_fit.py']
plan=dict(schema='paired-ensemble-targets-v1',train_seed=3510000000,policy_seed=6510000000,train_games=5000,replicates=2,teacher_iterations=800,threads=14,epochs=10,training_seed=800000009,control_seed=3560000000,lineage_seed=3570000000,milestone_seed=3580000000,champion_sha256=EXPECTED,script_sha256=sha(__file__),scripts_sha256={n:sha(ROOT/'research'/n) for n in SCRIPTS},collector_sha256=sha(ROOT/'crates/splendor-arena/examples/flywheel_data.rs'),original_train_sha256=sha(ROOT/'local/research/e58/train.bin'),dev_sha256=sha(ROOT/'local/research/e58/dev.bin'),replay_sha256=sha(ROOT/'local/research/e56/train.bin'))
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
start=time.monotonic();assert sha(FIXED/'model.bin')==EXPECTED
env=os.environ.copy();env.update(CARGO_BUILD_JOBS='2',CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),SPLENDOR_BEST_MODEL=str(FIXED/'model.bin'))
def run(command,name,allowed=(0,)):
 t=time.monotonic()
 with (OUT/name).open('w') as f:r=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
 with (OUT/'events.jsonl').open('a') as f:f.write(json.dumps(dict(stage=name,seconds=time.monotonic()-t,exit_code=r.returncode,command=list(map(str,command))))+'\n')
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit{r.returncode}; evidence retained')
for n in SCRIPTS:shutil.copy2(ROOT/'research'/n,OUT/n)
shutil.copy2(ROOT/'crates/splendor-arena/examples/flywheel_data.rs',OUT/'flywheel_data.rs')
run([BIN/'examples/flywheel_data','--games',5000,'--seed',3510000000,'--policy-seed',6510000000,'--iterations',800,'--depth',16,'--threads',14,'--teacher-replicates',2,'--output',LOCAL/'train.bin'],'collection.log')
original=np.memmap(ROOT/'local/research/e58/train.bin',mode='r',dtype=DTYPE);ensemble=np.memmap(LOCAL/'train.bin',mode='r',dtype=DTYPE)
a=json.loads((ROOT/'research/e58/train.json').read_text());b=json.loads((LOCAL/'train.json').read_text());assert a['records']==b['records'] and len(original)==len(ensemble)
for offset in range(0,len(original),8192):
 x=original[offset:offset+8192];y=ensemble[offset:offset+8192]
 for n in ['setup','x','mask','outcome']:assert np.array_equal(x[n],y[n],equal_nan=True)
 assert np.isfinite(y['policy']).all() and np.allclose(y['policy'].sum(1),1,atol=1e-5)
 assert np.all(y['policy'][y['mask']==0]==0)
assert sha(ROOT/'local/research/e58/train.bin')==plan['original_train_sha256']
shutil.copy2(LOCAL/'train.json',OUT/'train.json')
(OUT/'paired-data-validation.json').write_text(json.dumps(dict(rows=len(original),games=5000,same_trajectories_inputs_masks_outcomes=True,ensemble_sha256=sha(LOCAL/'train.bin'),original_sha256=plan['original_train_sha256']),indent=2)+'\n')
assert sha(ROOT/'local/research/e58/dev.bin')==plan['dev_sha256'];assert sha(ROOT/'local/research/e56/train.bin')==plan['replay_sha256']
for n,h in plan['scripts_sha256'].items():assert sha(ROOT/'research'/n)==h
run([sys.executable,ROOT/'research/train_flywheel.py','--train',ROOT/'local/research/e56/train.bin',LOCAL/'train.bin','--dev',ROOT/'local/research/e58/dev.bin','--output',OUT/'model','--warmstart',FIXED/'model.pt','--epochs',10,'--batch-size',1024,'--device','mps','--seed',800000009,'--selection','outcome','--learning-rate',0.0001],'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
while not (ROOT/'research/e59/completed.json').exists():
 if time.monotonic()-start>14400:raise RuntimeError('E59 incomplete; no dependent endpoint selection')
 time.sleep(10)
parent=json.loads((ROOT/'research/e59/endpoint.json').read_text());assert sha(parent['model'])==parent['model_sha256']
(OUT/'parent.json').write_text(json.dumps(parent,indent=2)+'\n');endpoint=parent
env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin')
def screen(baseline,seed,name):
 env['SPLENDOR_BEST_MODEL']=str(baseline)
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',seed,'--output',OUT/name],name+'.log',(0,2))
 report=json.loads((OUT/name/'screen.json').read_text());assert report['seed']==seed and report['requested_games']==2000
 result=provisional_decision(report);result['strict_decision']=json.loads((OUT/name/'decision.json').read_text());return result
control=screen(ROOT/'research/e58/model/model.bin',3560000000,'control-gate');lineage=control
if control['selected'] and parent['model_sha256']!=sha(ROOT/'research/e58/model/model.bin'):
 lineage=screen(parent['model'],3570000000,'lineage-gate')
if control['selected'] and lineage['selected']:
 endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage; milestone pending')
result=dict(control=control,lineage=lineage,selected=endpoint!=parent,parent_sha256=parent['model_sha256'],candidate_sha256=m['model_sha256'])
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
# The endpoint is frozen before fresh milestone outcomes.
assert sha(endpoint['model'])==endpoint['model_sha256'];assert sha(FIXED/'model.bin')==EXPECTED
env['SPLENDOR_BEST_MODEL']=str(FIXED/'model.bin');env['SPLENDOR_CANDIDATE_MODEL']=endpoint['model']
run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',20000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',3580000000,'--output',OUT/'milestone'],'milestone.log',(0,2))
milestone=json.loads((OUT/'milestone/decision.json').read_text());milestone['confirmed']=milestone['decision']=='promote'
(OUT/'milestone-decision.json').write_text(json.dumps(milestone,indent=2)+'\n')
(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,decision=result,milestone=milestone,seconds=time.monotonic()-start),indent=2)+'\n');print(json.dumps(dict(decision=result,milestone=milestone)))
