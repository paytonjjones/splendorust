"""Paired E55 control, serial after E54, with frozen champion and original labels."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
from collect_evidence import validate_report
OUT=ROOT/'research/e55';DATA=ROOT/'local/research/e54/flywheel';BIN=ROOT/'local/research/flywheel-target/release'
CHAMPION=ROOT/'research/e41/cycle-0/model'
EXPECTED='d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600'
assert sha(CHAMPION/'model.bin')==EXPECTED
scripts={p:sha(ROOT/'research'/p) for p in ['train_flywheel.py','flywheel_model.py','encoding_views.py','lineage.py']}
plan=dict(schema='paired-views-v1',seed=1320000000,training_seed=800000007,epochs=10,champion_sha256=EXPECTED,script_sha256=sha(__file__),training_scripts_sha256=scripts,rule='requested worst-case point credit >50.5%; provisional only; strict decision preserved',paired_data='E54 five train shards and separate development shard; original labels/order')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
start=time.monotonic()
while not (DATA/'completed.json').exists():
 if time.monotonic()-start>3600:raise RuntimeError('E54 did not finish; no dependent training run')
 time.sleep(10)
for name,h in scripts.items():assert sha(ROOT/'research'/name)==h,'training source changed while waiting'
local=DATA/'cycle-000';public=ROOT/'research/e54'
shutil.copytree(local/'model',public/'model',dirs_exist_ok=True)
shutil.copytree(local/'gate',public/'gate',dirs_exist_ok=True) if (local/'gate').exists() else None
for name in ['decision.json','teacher.json','training.log','parity.log','gate.log']:
 if (local/name).exists():shutil.copy2(local/name,public/name)
for name in ['completed.json','best.json','events.jsonl']:
 if (DATA/name).exists():shutil.copy2(DATA/name,public/name)
baseline=json.loads((DATA/'best.json').read_text());assert sha(baseline['model'])==baseline['model_sha256']
(OUT/'baseline.json').write_text(json.dumps(baseline,indent=2)+'\n')
train=sorted((local/'train').glob('*.bin'));train=[p for p in train if not p.name.endswith('.views.bin')]
dev=sorted((local/'dev').glob('*.bin'));dev=[p for p in dev if not p.name.endswith('.views.bin')]
assert len(train)==5 and len(dev)==1
for name in scripts:shutil.copy2(ROOT/'research'/name,OUT/name)
def run(command,name,allowed=(0,),env=None):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit{r.returncode}')
run([sys.executable,ROOT/'research/train_flywheel.py','--train',*train,'--dev',*dev,'--output',OUT/'model','--warmstart',CHAMPION/'model.pt','--epochs',10,'--batch-size',1024,'--device','mps','--seed',800000007,'--selection','outcome','--learning-rate',0.0001,'--sample-encoding-views'],'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());assert sha(OUT/'model/model.bin')==m['model_sha256']
run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
if m['best_epoch']==0:
 result=dict(selected=False,reason='unchanged warm-start function; no new learning candidate',champion_sha256=EXPECTED)
else:
 env=os.environ.copy();env['CARGO_TARGET_DIR']=str(ROOT/'local/research/flywheel-target');env['SPLENDOR_BEST_MODEL']=baseline['model'];env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin');env['CARGO_BUILD_JOBS']='2'
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',1320000000,'--output',OUT/'gate'],'gate.log',(0,2),env)
 report=json.loads((OUT/'gate/screen.json').read_text());validate_report(report)
 assert report['seed']==1320000000 and report['requested_games']==2000 and report['run_config']['names']==['flywheel-candidate','flywheel-best']
 strict=json.loads((OUT/'gate/decision.json').read_text());result=provisional_decision(report)
 result.update(strict_decision=strict,champion_sha256=EXPECTED,baseline_sha256=baseline['model_sha256'],candidate_sha256=m['model_sha256'],training_seconds=m['seconds'],gate_seconds=report['runtime_seconds'])
 if result['selected']:baseline=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage; no champion promotion')
assert sha(CHAMPION/'model.bin')==EXPECTED
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'best.json').write_text(json.dumps(baseline,indent=2)+'\n')
(OUT/'completed.json').write_text(json.dumps(dict(best=baseline,seconds=time.monotonic()-start),indent=2)+'\n')
print(json.dumps(result),flush=True)
