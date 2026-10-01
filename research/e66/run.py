"""Fresh measured-cost diagnostic using the evaluator's immutable native harness."""
import json,subprocess,sys,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e66';EVAL=Path('/Users/payton.jones/.codex/worktrees/90ce/splendorust');HARNESS=EVAL/'benchmarks/strength/native';PYTHON=EVAL/'local/strength/inference/bin/python';MODEL=ROOT/'research/e56/model/model.bin'
assert sha(MODEL)=='055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41'
files=[HARNESS/p for p in ['run.py','schedule.py','upstream.py','validate.py','replay.py','summarize.py']]+[EVAL/'benchmarks/strength/summarize.py',EVAL/'target/release/examples/native_policy_worker']
expected={str(p):sha(p) for p in files}
plan=dict(profile='alphazero-native-32a27ac-v1',games=400,master=4200000000,iterations=2048,workers=4,model_sha256=sha(MODEL),source_revision=subprocess.check_output(['git','-C',str(EVAL),'rev-parse','HEAD'],text=True).strip(),harness_sha256=expected,script_sha256=sha(__file__),scope='Frozen E56 search-budget diagnostic; native rules; no promotion or canonical rank')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for p in files[:-1]:shutil.copy2(p,OUT/('diagnostic-summary.py' if p==EVAL/'benchmarks/strength/summarize.py' else 'native-run.py' if p.name=='run.py' else p.name))
shutil.copy2(HARNESS/'README.md',OUT/'PROFILE.md')
start=time.monotonic()
def run(args,name):
 with (OUT/name).open('w') as f:subprocess.run(list(map(str,args)),cwd=EVAL,stdout=f,stderr=subprocess.STDOUT,check=True)
run([PYTHON,HARNESS/'schedule.py','--games',400,'--master',4200000000,'--workers',4,'--iterations',2048,'--model',MODEL,'--output',OUT/'arena'],'schedule.log')
assert all(sha(p)==h for p,h in expected.items()),'harness changed during diagnostic'
for script,output in [('replay.py','replay.json'),('summarize.py','summary.json')]:run([PYTHON,HARNESS/script,OUT/'arena/games.jsonl','--output',OUT/output],script+'.log')
s=json.loads((OUT/'summary.json').read_text());r=json.loads((OUT/'replay.json').read_text());assert s['games']==400 and r['checked_games']==400
(OUT/'completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,credit=s['candidate_credit_conditional_rate'],requested_bounds=s['all_requested_credit_bounds'],ci95=s['paired_bootstrap95_missing_envelope'],statuses=s['statuses'],replayed=r['checked_games']),indent=2)+'\n')
print((OUT/'completed.json').read_text())
