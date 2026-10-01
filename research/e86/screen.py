"""Verify native export and root cost, then run the fixed paired screen."""
import json,os,subprocess,sys,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);OUT=ROOT/'research/e86';MODEL=OUT/'model'
while not (MODEL/'manifest.json').exists():time.sleep(10)
fixture=json.loads((MODEL/'parity.json').read_text());fixture['context']=[row[-7:] for row in fixture['context']]
(MODEL/'parity-public.json').write_text(json.dumps(fixture)+'\n')
with (OUT/'native-trained-parity.json').open('w') as f:subprocess.run([ROOT/'local/research/flywheel-target/release/examples/transfer_parity',MODEL/'model.bin',MODEL/'parity-public.json','real'],stdout=f,stderr=subprocess.STDOUT,check=True)
env=os.environ.copy();env.update(SPLENDOR_BEST_MODEL=str(ROOT/'research/e81/model/model.bin'),SPLENDOR_CANDIDATE_MODEL=str(MODEL/'model.bin'),CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2')
with (OUT/'trained-cost.jsonl').open('w') as f:subprocess.run([ROOT/'local/research/e86-cost'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
rows=[json.loads(s) for s in (OUT/'trained-cost.jsonl').read_text().splitlines()];ratios=[]
for i in range(3):
 a=next(r for r in rows if r['repeat']==i and 'candidate' in r['agent']);b=next(r for r in rows if r['repeat']==i and 'candidate' not in r['agent']);assert a['simulations']==b['simulations']==568*128;ratios.append(a['seconds']/b['seconds'])
median=statistics.median(ratios);(OUT/'cost-summary.json').write_text(json.dumps(dict(ratios=ratios,median_ratio=median,limit=1.15,passes=median<=1.15,shared_host=True),indent=2)+'\n');assert median<=1.15,'root cost exceeds preregistered cap'
command=[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-root-gumbel-candidate','--baseline','flywheel-gumbel','--screen','2000','--confirm','0','--seed','4670000000','--threads','14','--iterations','128','--depth','16','--output',OUT/'gate']
with (OUT/'gate.log').open('w') as f:result=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
assert (OUT/'gate/decision.json').exists();print(json.dumps(dict(returncode=result.returncode,decision=json.loads((OUT/'gate/decision.json').read_text()))),flush=True)
