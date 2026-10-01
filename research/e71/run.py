"""Matched-data test of the missing public reservation information."""
import os,sys,json,time,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e71';BASE=ROOT/'research/e59/model';PARENT=ROOT/'research/e68/model';BIN=ROOT/'local/research/flywheel-target/release'
train=[ROOT/'local/research/e64/train.bin',*[ROOT/'local/research/e68/train'/f'{i:06}.bin' for i in range(0,5000,1000)]];dev=ROOT/'local/research/e68/dev.bin'
scripts=['train_flywheel.py','flywheel_model.py','lineage.py','distillation_fit.py','encoding_views.py']
plan=dict(schema='matched-public-information-distillation-v1',train=[dict(path=str(p),sha256=sha(p),context_sha256=sha(p.with_suffix('.context.bin'))) for p in train],dev=dict(path=str(dev),sha256=sha(dev),context_sha256=sha(dev.with_suffix('.context.bin'))),base_sha256=sha(BASE/'model.bin'),base_checkpoint_sha256=sha(BASE/'model.pt'),parent_sha256=sha(PARENT/'model.bin'),champion_sha256=sha(ROOT/'research/e56/model/model.bin'),training_seed=800000013,screen_seed=4270000000,epochs=10,batch_size=1024,learning_rate=1e-4,screen_games=2000,screen_iterations=128,threads=14,scripts={p:sha(ROOT/'research'/p) for p in scripts},script_sha256=sha(__file__),rule='Identical E68 labels, datasets, initialization, training seed and optimizer; only append public context. Provisional requested-credit point >50.5%; champion unchanged.')
assert not (OUT/'plan.json').exists(),'immutable one-shot experiment'
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for p in scripts:shutil.copy2(ROOT/'research'/p,OUT/p)
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2',SPLENDOR_BEST_MODEL=str(PARENT/'model.bin'))
start=time.monotonic()
def run(cmd,log,allowed=(0,)):
 with (OUT/log).open('w') as f:r=subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT)
 assert r.returncode in allowed,f'{log}: exit {r.returncode}'
run([sys.executable,ROOT/'research/train_flywheel.py','--train',*train,'--dev',dev,'--output',OUT/'model','--warmstart',BASE/'model.pt','--public-context','--epochs',10,'--batch-size',1024,'--device','mps','--seed',800000013,'--selection','outcome','--learning-rate',0.0001],'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());assert m['public_context'] and m['parameters']==142462
assert all(sha(ROOT/'research'/p)==h for p,h in plan['scripts'].items()),'training source changed'
run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'model/model.bin')
run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',4270000000,'--output',OUT/'gate'],'gate.log',(0,2))
r=json.loads((OUT/'gate/screen.json').read_text());assert r['seed']==4270000000 and r['requested_games']==2000
result=provisional_decision(r);result.update(strict_decision=json.loads((OUT/'gate/decision.json').read_text()),parent_sha256=plan['parent_sha256'],candidate_sha256=m['model_sha256'],champion_sha256=plan['champion_sha256'])
endpoint=dict(model=str(PARENT/'model.bin'),checkpoint=str(PARENT/'model.pt'),model_sha256=plan['parent_sha256'],checkpoint_sha256=sha(PARENT/'model.pt'))
if result['selected']:endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional only; milestone pending')
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
run([sys.executable,ROOT/'research/distillation_fit.py','--train',*train[1:],'--dev',dev,'--checkpoint',OUT/'model/model.pt','--output',OUT/'fit-diagnostic.json'],'fit.log')
assert sha(ROOT/'research/e56/model/model.bin')==plan['champion_sha256']
(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,decision=result,seconds=time.monotonic()-start),indent=2)+'\n');print(json.dumps(result),flush=True)
