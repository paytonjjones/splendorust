import os,sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
out=ROOT/'research/e89';local=ROOT/'local/research/e89';local.mkdir(exist_ok=True)
env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin');binary=ROOT/'local/research/flywheel-target/release/examples/flywheel_data'
checks={}
for name,flags,expected in [('legacy',[],'a80e5b35d340356fc8953371e1cb5f13c168ec4a8e3f52bde38c0916da9293a4'),('teacher',['--actor-iterations',128,'--actor-agent','flywheel-best','--teacher-agent','flywheel-gumbel-noisy'],'83a727477589fc2ee42becca42b960768d7e2454326fe3fb1e940e6c5b266559')]:
 with (out/(name+'.log')).open('w') as log:subprocess.run(list(map(str,[binary,'--games',16,'--seed',3630000000,'--policy-seed',6630000000,'--iterations',800,'--depth',16,'--threads',14,*flags,'--output',local/(name+'.bin')])),env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 actual=sha(local/(name+'.bin'));assert actual==expected,(name,actual);checks[name]=dict(byte_exact=True,sha256=actual)
(out/'legacy-checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks))
