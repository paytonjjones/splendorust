"""Resume unplayed screen after fixing diagnostic-example Clippy failure."""
import os,sys,json,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
from lineage import provisional_decision
OUT=ROOT/'research/e68';plan=json.loads((OUT/'plan.json').read_text());m=json.loads((OUT/'model/manifest.json').read_text());start=time.monotonic()
assert not (OUT/'gate/screen.json').exists(),'do not reuse played seeds'
assert sha(OUT/'model/model.bin')==m['model_sha256']
assert sha('research/e59/model/model.bin')==plan['base_sha256']
(OUT/'gate').rename(OUT/'gate-build-failure');(OUT/'gate.log').rename(OUT/'gate-build-failure.log')
env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2',SPLENDOR_BEST_MODEL=str(ROOT/'research/e59/model/model.bin'),SPLENDOR_CANDIDATE_MODEL=str(OUT/'model/model.bin'))
command=[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-candidate','--baseline','flywheel-best','--screen',2000,'--confirm',0,'--threads',14,'--iterations',128,'--depth',16,'--seed',4230000000,'--output',OUT/'gate']
with (OUT/'gate.log').open('w') as f:r=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode in (0,2) and (OUT/'gate/screen.json').exists(),'screen failed; preserve evidence'
report=json.loads((OUT/'gate/screen.json').read_text());assert report['seed']==4230000000 and report['requested_games']==2000
result=provisional_decision(report);result['strict_decision']=json.loads((OUT/'gate/decision.json').read_text());result.update(parent_sha256=plan['base_sha256'],candidate_sha256=m['model_sha256'],champion_sha256=plan['champion_sha256'])
endpoint=dict(model=str(ROOT/'research/e59/model/model.bin'),checkpoint=str(ROOT/'research/e59/model/model.pt'),model_sha256=plan['base_sha256'],checkpoint_sha256=plan['base_checkpoint_sha256'])
if result['selected']:endpoint=dict(model=str(OUT/'model/model.bin'),checkpoint=str(OUT/'model/model.pt'),model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional only; milestone pending')
(OUT/'decision.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
train=sorted((ROOT/'local/research/e68/train').glob('*.bin'))
command=[sys.executable,ROOT/'research/distillation_fit.py','--train',*train,'--dev',ROOT/'local/research/e68/dev.bin','--checkpoint',OUT/'model/model.pt','--output',OUT/'fit-diagnostic.json']
with (OUT/'fit.log').open('w') as f:subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
(OUT/'completed.json').write_text(json.dumps(dict(endpoint=endpoint,decision=result,resume_seconds=time.monotonic()-start,resume_reason='Diagnostic example failed Clippy before any screen games; seeds remained unused'),indent=2)+'\n');print(json.dumps(result),flush=True)
