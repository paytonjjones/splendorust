import os,sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));os.chdir(ROOT)
import numpy as np
from flywheel_model import DTYPE,sha,check_rows
OUT=ROOT/'research/e81';LOCAL=ROOT/'local/research/e81/check';LOCAL.mkdir(parents=True,exist_ok=True);env=os.environ.copy();binary=ROOT/'local/research/flywheel-target/release/examples/flywheel_data'
def run(name,args):
 with (OUT/(name+'.log')).open('w') as log:subprocess.run(list(map(str,[binary,*args,'--output',LOCAL/(name+'.bin')])),env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin')
run('legacy',['--games',16,'--seed',3630000000,'--policy-seed',6630000000,'--iterations',800,'--depth',16,'--threads',14]);assert sha(LOCAL/'legacy.bin')=='a80e5b35d340356fc8953371e1cb5f13c168ec4a8e3f52bde38c0916da9293a4'
env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e68/model/model.bin')
flags=['--games',16,'--seed',4300000000,'--policy-seed',7300000000,'--iterations',800,'--actor-iterations',128,'--actor-agent','flywheel-gumbel','--teacher-agent','flywheel-gumbel','--teacher-action-targets','--depth',16]
run('teacher-action',flags+['--threads',14]);run('serial',flags+['--threads',1]);assert sha(LOCAL/'teacher-action.bin')==sha(LOCAL/'serial.bin')
a=np.memmap(LOCAL/'teacher-action.bin',dtype=DTYPE,mode='r');b=np.memmap(ROOT/'local/research/e74/train/000000.bin',dtype=DTYPE,mode='r')[:len(a)]
for field in ['setup','x','mask','outcome']:assert np.array_equal(a[field],b[field],equal_nan=True),field
check_rows(a);assert np.all((a['policy']==0)|(a['policy']==1)) and np.all(a['policy'].sum(axis=1)==1)
assert not np.array_equal(a['policy'],b['policy']);meta=json.loads((LOCAL/'teacher-action.json').read_text());assert meta['complete']==16 and meta['teacher_action_targets']
result=dict(legacy_byte_exact=True,actor_setup_input_mask_outcome_exact=True,legal_onehot_targets=True,serial_parallel_byte_exact=True,complete=16,rows=len(a),data_sha256=sha(LOCAL/'teacher-action.bin'),binary_sha256=sha(binary),model_sha256=sha(ROOT/'research/e68/model/model.bin'))
(OUT/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
