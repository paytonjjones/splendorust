"""Fixed frozen-endpoint native controls and unchanged AlphaZero supporting profile."""
import os,json,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);OUT=ROOT/'research/e57'
start=time.monotonic()
while not (ROOT/'research/e56/endpoint.json').exists():
 if time.monotonic()-start>7200:raise RuntimeError('No frozen endpoint')
 time.sleep(10)
endpoint=json.loads((ROOT/'research/e56/endpoint.json').read_text());model=Path(endpoint['model'])
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(model)==endpoint['model_sha256']
(OUT/'endpoint.json').write_text(json.dumps(endpoint,indent=2)+'\n')
env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(model),SPLENDOR_BEST_MODEL=str(model),CARGO_BUILD_JOBS='2')
plan=dict(model_sha256=sha(model),native_screens=[['search128',128,3420000000],['search128',16,3430000000],['strong',128,3440000000]],external=dict(games=400,seed=3450000,policy_seed=2500001,sampling_seed=3500001,iterations=800,depth=16,external_iterations=0,cap=2000),script_sha256=sha(__file__),harness_sha256=sha(ROOT/'benchmarks/strength/run.py'),overlap='Fixed-budget milestone and controls may overlap; timings conditional on shared CPU load')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
# External process runs alongside the fixed-budget native controls.
external_log=(OUT/'external.log').open('w')
external=subprocess.Popen([sys.executable,ROOT/'benchmarks/strength/run.py','--external','alphazero','--candidate','flywheel-candidate','--players','2','--games','400','--seed','3450000','--policy-seed','2500001','--sampling-seed','3500001','--iterations','800','--depth','16','--external-iterations','0','--cap','2000','--stage','confirmation','--output',OUT/'alphazero.jsonl'],env=env,stdout=external_log,stderr=subprocess.STDOUT)
(OUT/'external-pid.json').write_text(json.dumps(dict(pid=external.pid),indent=2)+'\n')
bin=ROOT/'local/research/flywheel-target/release'
with (OUT/'decision-cost.jsonl').open('w') as log:
 subprocess.run([bin/'examples/endpoint_cost'],env=env,stdout=log,check=True)
for baseline,iterations,seed in plan['native_screens']:
 name=f'{baseline}-nn{iterations}'
 with (OUT/(name+'.log')).open('w') as log:
  r=subprocess.run([bin/'splendor','compare','--agent-a','flywheel-candidate','--agent-b',baseline,'--games','2000','--iterations',str(iterations),'--depth','16','--threads','14','--seed',str(seed),'--output',OUT/(name+'.json')],env=env,stdout=log,stderr=subprocess.STDOUT)
  if r.returncode not in [0,2]:raise RuntimeError(f'{name}: exit{r.returncode}')
code=external.wait();external_log.close()
if code:raise RuntimeError(f'external benchmark exited{code}')
subprocess.run([sys.executable,ROOT/'benchmarks/strength/summarize.py',OUT/'alphazero.jsonl','--output',OUT/'alphazero-summary.json'],check=True)
assert sha(model)==endpoint['model_sha256']
(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,model_sha256=sha(model)),indent=2)+'\n')
