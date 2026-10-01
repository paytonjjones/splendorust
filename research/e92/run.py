"""Frozen current-champion external check; no training or policy tuning."""
import json,os,subprocess,hashlib,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);OUT=ROOT/'research/e92'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
champ=json.loads((ROOT/'research/CHAMPION.json').read_text());assert champ['model_sha256']=='e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8'
model=ROOT/champ['model'];assert sha(model)==champ['model_sha256'];assert champ['search_agent']=='flywheel-gumbel' and champ['iterations']==128
source=ROOT/'local/strength/external/alphazero';assert subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()=='32a27ac1f85d5de2766cc5f60c2bf04e557f7836'
assert not subprocess.check_output(['git','-C',source,'status','--porcelain','--untracked-files=no'],text=True).strip()
checkpoint=source/'splendor/pretrained_2players.pt';assert sha(checkpoint)=='6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07'
workers=[ROOT/'target/release/examples'/n for n in ['native_policy_worker','native_rules_probe','strength_worker']]
paths=[ROOT/'research/CHAMPION.json',model,checkpoint,*workers,*[ROOT/'crates/splendor-agents/src'/n for n in ['environment.rs','native_environment.rs','neural_search.rs','transfer.rs','belief.rs']],ROOT/'crates/splendor-arena/examples/native_policy_worker.rs',ROOT/'benchmarks/strength/native/run.py',ROOT/'benchmarks/strength/native/schedule.py']
plan=dict(schema='current-champion-external-v1',champion=champ,master=4810000000,games=2000,workers=8,iterations=128,search='gumbel',root_only=False,profile='alphazero-native-32a27ac-v1',source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),files={str(p):sha(p) for p in paths},python=str(ROOT/'local/strength/inference/bin/python'),scope='Current canonical champion under unchanged native external profile; observation-only SR versus native-private AlphaZero800; no canonical/equal-information/equal-compute rank')
assert not (OUT/'plan.json').exists();(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for p in [ROOT/'crates/splendor-agents/src/environment.rs',ROOT/'crates/splendor-agents/src/native_environment.rs',ROOT/'crates/splendor-agents/src/neural_search.rs',ROOT/'crates/splendor-arena/examples/native_policy_worker.rs']:shutil.copy2(p,OUT/p.name)
start=time.monotonic();env=os.environ.copy();env.update(CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2')
def run(command,name):
 with (OUT/name).open('w') as f:subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
run(['cargo','test','--release','--workspace','--locked','--all-features'],'all-feature-tests.log')
run([plan['python'],ROOT/'benchmarks/strength/native/schedule.py','--games',2000,'--master',4810000000,'--workers',8,'--iterations',128,'--search','gumbel','--model',model,'--output',OUT/'arena'],'schedule.log')
run([plan['python'],ROOT/'benchmarks/strength/native/replay.py',OUT/'arena/games.jsonl','--output',OUT/'replay.json'],'replay.log')
run([plan['python'],ROOT/'benchmarks/strength/native/summarize.py',OUT/'arena/games.jsonl','--output',OUT/'summary.json'],'summary.log')
assert all(sha(p)==h for p,h in plan['files'].items()),'frozen input changed'
(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,summary=json.loads((OUT/'summary.json').read_text()),replay=json.loads((OUT/'replay.json').read_text())),indent=2)+'\n')
