"""Check that the current operator supplies a genuinely stronger teacher."""
import os,sys,json,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e76';MODEL=ROOT/'research/e68/model/model.bin';start=time.monotonic()
plan=dict(model_sha256=sha(MODEL),candidate='flywheel-gumbel800',baseline='flywheel-gumbel',candidate_iterations=800,baseline_iterations=128,depth=16,root_noise=0,seed=4490000000,games=2000,threads=14,script_sha256=sha(__file__),search_sha256=sha(ROOT/'crates/splendor-agents/src/neural_search.rs'),factory_sha256=sha(ROOT/'crates/splendor-agents/src/lib.rs'),scope='Teacher strength diagnosis; frozen model, no learning, model promotion or public rank')
assert not (OUT/'plan.json').exists();(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
env=os.environ.copy();env.update(SPLENDOR_BEST_MODEL=str(MODEL),CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2')
with (OUT/'gate.log').open('w') as f:r=subprocess.run(list(map(str,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel800','--baseline','flywheel-gumbel','--screen',2000,'--confirm',0,'--iterations',128,'--depth',16,'--threads',14,'--seed',4490000000,'--output',OUT/'gate'])),env=env,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode in (0,2) and (OUT/'gate/screen.json').exists()
s=json.loads((OUT/'gate/screen.json').read_text());assert s['seed']==4490000000 and s['requested_games']==2000
result=dict(credit=s['agents'][0]['win_rate'],ci95=s['agents'][0]['ci95'],complete=s['completed_games'],requested=s['requested_games'],runtime_seconds=s['runtime_seconds'],strict_decision=json.loads((OUT/'gate/decision.json').read_text()),scope=plan['scope'],seconds=time.monotonic()-start)
assert sha(MODEL)==plan['model_sha256'] and sha(ROOT/'crates/splendor-agents/src/lib.rs')==plan['factory_sha256']
(OUT/'completed.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
