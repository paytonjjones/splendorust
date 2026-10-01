"""Frozen model screen for the new policy improvement search."""
import os,sys,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e73';MODEL=ROOT/'research/e68/model/model.bin';start=time.monotonic()
plan=dict(schema='gumbel-search-screen-v1',model_sha256=sha(MODEL),candidate='flywheel-gumbel',baseline='flywheel-best',seed=4290000000,games=2000,iterations=128,depth=16,threads=14,script_sha256=sha(__file__),search_sha256=sha(ROOT/'crates/splendor-agents/src/neural_search.rs'),root_noise=0,cvisit=50,cscale=0.1,max_considered=16,rule='Search-only frozen-model comparison. No model learning or champion change; paper exact-value guarantee not assumed.')
assert not (OUT/'plan.json').exists()
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
env=os.environ.copy();env.update(SPLENDOR_BEST_MODEL=str(MODEL),CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2')
with (OUT/'gate.log').open('w') as f:r=subprocess.run(list(map(str,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--iterations',128,'--depth',16,'--threads',14,'--seed',4290000000,'--output',OUT/'gate'])),env=env,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode in (0,2) and (OUT/'gate/screen.json').exists()
report=json.loads((OUT/'gate/screen.json').read_text());assert report['requested_games']==2000 and report['seed']==4290000000
result=provisional_decision(report);result.update(strict_decision=json.loads((OUT/'gate/decision.json').read_text()),model_sha256=sha(MODEL),scope='Search-only; no learned gain or champion promotion')
assert sha(ROOT/'crates/splendor-agents/src/neural_search.rs')==plan['search_sha256']
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,decision=result),indent=2)+'\n');print(json.dumps(result),flush=True)
