"""Fixed-base capacity test; choose a measured-cost budget before arena results."""
import os,sys,json,subprocess,shutil,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e63';BIN=ROOT/'local/research/flywheel-target/release';BASE=ROOT/'research/e59/model';start=time.monotonic()
assert sha(BASE/'model.bin')=='76d45006d332dcd80635150f23917c321245f49cfb10a8e77654d3096505a918'
train=[ROOT/'local/research/e56/train.bin',ROOT/'local/research/e58/train.bin'];dev=ROOT/'local/research/e58/dev.bin'
scripts=['train_flywheel.py','flywheel_model.py','gated_model.py','residual_model.py','lineage.py']
plan=dict(schema='residual-capacity-v1',base_sha256=sha(BASE/'model.bin'),base_checkpoint_sha256=sha(BASE/'model.pt'),train=[dict(path=str(p),sha256=sha(p)) for p in train],dev=dict(path=str(dev),sha256=sha(dev)),epochs=20,training_seed=800000011,batch_size=1024,learning_rate=1e-4,screen_seeds=[3610000000,3620000000],games=2000,threads=14,budget_rule='largest multiple of eight with median decision cost <= 1.05 * E59 NN128; selected before outcomes',script_sha256=sha(__file__),source_sha256={p:sha(ROOT/'research'/p) for p in scripts})
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for p in scripts:shutil.copy2(ROOT/'research'/p,OUT/p)
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2',SPLENDOR_BEST_MODEL=str(BASE/'model.bin'),SPLENDOR_CANDIDATE_MODEL=str(OUT/'model/model.bin'))
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as log:r=subprocess.run(list(map(str,command)),env=env,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit {r.returncode}')
run([sys.executable,ROOT/'research/train_flywheel.py','--train',*train,'--dev',dev,'--output',OUT/'model','--warmstart',BASE/'model.pt','--architecture','residual','--epochs',20,'--batch-size',1024,'--device','mps','--seed',800000011,'--selection','outcome','--learning-rate',0.0001],'training.log')
m=json.loads((OUT/'model/manifest.json').read_text());assert m['fixed_base_exact'] and m['base_model_sha256']==plan['base_sha256']
run([BIN/'examples/transfer_parity',OUT/'model/model.bin',OUT/'model/parity.json','real'],'parity.log')
if m['best_epoch']==0:
 (OUT/'completed.json').write_text(json.dumps(dict(selected=False,reason='epoch zero selected; initial base function unchanged; no arena self-comparison',seconds=time.monotonic()-start),indent=2)+'\n');sys.exit(0)
run([BIN/'examples/endpoint_cost','--budget-sweep'],'cost.jsonl')
rows=[json.loads(s) for s in (OUT/'cost.jsonl').read_text().splitlines()]
base=statistics.median(r['seconds']/r['decisions'] for r in rows if r['agent']=='flywheel-best128')
costs={n:statistics.median(r['seconds']/r['decisions'] for r in rows if r['agent']=='flywheel-candidate' and r['iterations']==n) for n in range(8,129,8)}
assert costs[128]>1.05*base,'expand timing range before viewing arena outcomes'
valid=[n for n,c in costs.items() if c<=1.05*base];assert valid,'no valid cost budget'
budget=max(valid)
(OUT/'cost-decision.json').write_text(json.dumps(dict(base_median_seconds=base,candidate_medians=costs,budget=budget,chosen_before_arena=True,cost_records_sha256=sha(OUT/'cost.jsonl')),indent=2)+'\n')
results={}
for name,iterations,seed in [('fixed',128,3610000000),('cost',budget,3620000000)]:
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best128','--screen',2000,'--confirm',0,'--threads',14,'--iterations',iterations,'--depth',16,'--seed',seed,'--output',OUT/('gate-'+name)],'gate-'+name+'.log',(0,2))
 report=json.loads((OUT/('gate-'+name)/'screen.json').read_text());assert report['seed']==seed and report['requested_games']==2000
 results[name]=dict(provisional=provisional_decision(report),strict=json.loads((OUT/('gate-'+name)/'decision.json').read_text()))
(OUT/'completed.json').write_text(json.dumps(dict(results=results,budget=budget,model_sha256=m['model_sha256'],seconds=time.monotonic()-start,champion_unchanged=True),indent=2)+'\n')
print((OUT/'completed.json').read_text(),flush=True)
