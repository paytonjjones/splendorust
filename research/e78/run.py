"""Fixed-base capacity test; choose a measured-cost budget before arena results."""
import os,sys,json,subprocess,shutil,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e78';BIN=ROOT/'local/research/flywheel-target/release';BASE=ROOT/'research/e68/model';start=time.monotonic()
assert sha(BASE/'model.bin')=='d199a3878d7feebb443cb8e01e4afee502e05f2e9ba34c7a042a6bb3b62b86f2'
train=[ROOT/'local/research/e68/train/004000.bin',*[ROOT/'local/research/e74/train'/f'{offset:06}.bin' for offset in range(0,5000,1000)]];dev=ROOT/'local/research/e74/dev.bin'
scripts=['train_flywheel.py','flywheel_model.py','gated_model.py','residual_model.py','lineage.py']
cost=json.loads((ROOT/'research/e77/cost-summary.json').read_text());assert cost['passes']
plan=dict(cost_precheck=cost,schema='root-residual-capacity-v1',base_sha256=sha(BASE/'model.bin'),base_checkpoint_sha256=sha(BASE/'model.pt'),train=[dict(path=str(p),sha256=sha(p)) for p in train],dev=dict(path=str(dev),sha256=sha(dev)),epochs=20,training_seed=800000015,batch_size=1024,learning_rate=1e-4,residual_width=384,residual_blocks=6,screen_seed=4510000000,games=2000,threads=14,iterations=128,depth=16,candidate='flywheel-root-gumbel-candidate',baseline='flywheel-gumbel',budget_rule='root correction once; frozen E68 leaves; if median decision cost exceeds 1.15x, require separate cost-matched screen before fast-loop selection',script_sha256=sha(__file__),source_sha256={p:sha(ROOT/'research'/p) for p in scripts})
assert not (OUT/'plan.json').exists(),'immutable one-shot experiment'
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for p in scripts:shutil.copy2(ROOT/'research'/p,OUT/p)
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2',SPLENDOR_BEST_MODEL=str(BASE/'model.bin'),SPLENDOR_CANDIDATE_MODEL=str(OUT/'model/model.bin'))
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit {r.returncode}')
run([sys.executable,ROOT/'research/train_flywheel.py','--train',*train,'--dev',dev,'--output',OUT/'model','--warmstart',BASE/'model.pt','--architecture','residual','--residual-width',384,'--residual-blocks',6,'--epochs',20,'--batch-size',1024,'--device','mps','--seed',800000015,'--selection','outcome','--learning-rate',0.0001],'training.log')
assert all(sha(ROOT/'research'/p)==h for p,h in plan['source_sha256'].items())
m=json.loads((OUT/'model/manifest.json').read_text());assert m['fixed_base_exact'] and m['base_model_sha256']==plan['base_sha256']
run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
if m['best_epoch']==0:
 (OUT/'completed.json').write_text(json.dumps(dict(selected=False,reason='epoch zero selected; initial base function unchanged; no arena self-comparison',seconds=time.monotonic()-start),indent=2)+'\n');sys.exit(0)
run([sys.executable,ROOT/'scripts/promote.py','--candidate',plan['candidate'],'--baseline',plan['baseline'],'--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',plan['screen_seed'],'--output',OUT/'gate'],'gate.log',(0,2))
r=json.loads((OUT/'gate/screen.json').read_text());result=provisional_decision(r);result['strict_decision']=json.loads((OUT/'gate/decision.json').read_text());result.update(parent_sha256=plan['base_sha256'],candidate_sha256=m['model_sha256'],root_only=True)
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'completed.json').write_text(json.dumps(dict(decision=result,seconds=time.monotonic()-start),indent=2)+'\n');print(json.dumps(result),flush=True)
