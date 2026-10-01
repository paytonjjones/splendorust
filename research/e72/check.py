"""Legacy byte parity and Gumbel teacher independence/parallel determinism."""
import os,sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
import numpy as np
from flywheel_model import DTYPE,sha,check_rows
OUT=ROOT/'research/e72';LOCAL=ROOT/'local/research/e72';LOCAL.mkdir(exist_ok=True)
env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin');binary=ROOT/'local/research/flywheel-target/release/examples/flywheel_data'
for name,flags,threads in [('legacy',[],14),('teacher',['--actor-iterations',128,'--actor-agent','flywheel-best','--teacher-agent','flywheel-gumbel-noisy'],14),('serial',['--actor-iterations',128,'--actor-agent','flywheel-best','--teacher-agent','flywheel-gumbel-noisy'],1)]:
 with (OUT/(name+'.log')).open('w') as f:subprocess.run(list(map(str,[binary,'--games',16,'--seed',3630000000,'--policy-seed',6630000000,'--iterations',800,'--depth',16,'--threads',threads,*flags,'--output',LOCAL/(name+'.bin')])),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
assert sha(LOCAL/'legacy.bin')=='a80e5b35d340356fc8953371e1cb5f13c168ec4a8e3f52bde38c0916da9293a4'
t=np.memmap(LOCAL/'teacher.bin',dtype=DTYPE,mode='r');old=np.memmap(ROOT/'local/research/e67/student.bin',dtype=DTYPE,mode='r')
assert len(t)==len(old)
for key in ['setup','x','mask','outcome']:assert np.array_equal(t[key],old[key],equal_nan=True),key
assert sha(LOCAL/'teacher.bin')==sha(LOCAL/'serial.bin');check_rows(t)
assert not np.array_equal(t['policy'],old['policy'])
for name in ['legacy','teacher','serial']:(OUT/(name+'.json')).write_text((LOCAL/(name+'.json')).read_text())
result=dict(legacy_byte_exact=True,actor_states_independent_of_teacher=True,serial_parallel_byte_exact=True,targets_legal_normalized=True,changed_policy_targets=True,rows=len(t),data_sha256=sha(LOCAL/'teacher.bin'),binary_sha256=sha(binary))
(OUT/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
