"""Fixed frozen-endpoint native controls and unchanged AlphaZero supporting profile."""
import os,json,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);OUT=ROOT/'research/e57'
sys.path.insert(0,str(ROOT/'scripts'))
from collect_evidence import validate_report
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
(OUT/'resume-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
# External process runs alongside the fixed-budget native controls.
external=None;external_log=None
if not (OUT/'alphazero.jsonl').exists():
 raise RuntimeError('Resume expects preserved external run; do not start duplicate games')
external_pid=json.loads((OUT/'external-pid.json').read_text())['pid']
bin=ROOT/'local/research/flywheel-target/release'
if len((OUT/'decision-cost.jsonl').read_text().splitlines())!=9:
 raise RuntimeError('Preserve cost probe and repair separately')
for baseline,iterations,seed in plan['native_screens']:
 name=f'{baseline}-nn{iterations}'
 path=OUT/(name+'.json')
 if not path.exists():
  with (OUT/(name+'.log')).open('w') as log:
   r=subprocess.run([bin/'splendor','compare','--agent-a','flywheel-candidate','--agent-b',baseline,'--games','2000','--iterations',str(iterations),'--depth','16','--threads','14','--seed',str(seed),'--output',path],env=env,stdout=log,stderr=subprocess.STDOUT)
  if r.returncode not in [0,1] or not path.exists():raise RuntimeError(f'{name}: execution failure')
 report=json.loads(path.read_text());validate_report(report)
 assert report['seed']==seed and report['requested_games']==2000 and report['run_config']['names']==['flywheel-candidate',baseline]
# Keep the original external process and exactly the original400-game schedule.
while True:
 try:os.kill(external_pid,0)
 except ProcessLookupError:break
 if time.monotonic()-start>7200:raise RuntimeError('External completion timeout; evidence retained')
 time.sleep(10)
rows=(OUT/'alphazero.jsonl').read_text().splitlines()
if len(rows)!=401:raise RuntimeError(f'External schedule unfinished: {len(rows)-1}/400')
subprocess.run([sys.executable,ROOT/'benchmarks/strength/summarize.py',OUT/'alphazero.jsonl','--output',OUT/'alphazero-summary.json'],check=True)
assert sha(model)==endpoint['model_sha256']
(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,model_sha256=sha(model)),indent=2)+'\n')
