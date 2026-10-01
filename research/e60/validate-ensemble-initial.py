import os,sys,json,time,subprocess,hashlib
from pathlib import Path
import numpy as np
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'research'));from flywheel_model import DTYPE
while not (ROOT/'research/e58/dev.json').exists():time.sleep(5)
env=os.environ.copy();env.update(CARGO_BUILD_JOBS='2',CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),SPLENDOR_BEST_MODEL=str(ROOT/'research/e56/model/model.bin'))
p=ROOT/'local/research/ensemble-check';out=ROOT/'research/e60'
with (out/'ensemble-build.log').open('w') as f:subprocess.run(['cargo','build','--release','--locked','-p','splendor-arena','--example','flywheel_data'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
for replicates in [1,4]:
 with (out/f'ensemble-{replicates}.log').open('w') as f:subprocess.run([ROOT/'local/research/flywheel-target/release/examples/flywheel_data','--games','16','--seed','3510000000','--policy-seed','6510000000','--iterations','800','--depth','16','--threads','14','--teacher-replicates',str(replicates),'--output',p/f'{replicates}.bin'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
a=np.memmap(p/'1.bin',dtype=DTYPE,mode='r');b=np.memmap(p/'4.bin',dtype=DTYPE,mode='r');ra=json.loads((p/'1.json').read_text());rb=json.loads((p/'4.json').read_text());orig=json.loads((ROOT/'research/e58/train.json').read_text())
assert ra['records']==rb['records']==orig['records'][:16]
with (ROOT/'local/research/e58/train.bin').open('rb') as f:prefix=f.read(len(a)*DTYPE.itemsize)
assert prefix==(p/'1.bin').read_bytes()
for name in ['setup','x','mask','outcome']:assert np.array_equal(a[name],b[name],equal_nan=True)
assert np.isfinite(b['policy']).all() and np.allclose(b['policy'].sum(1),1,atol=1e-5) and np.all(b['policy'][b['mask']==0]==0)
assert np.isfinite(b['teacher']).all() and np.all((b['teacher']>=0)&(b['teacher']<=1))
assert np.any(a['policy']!=b['policy']) and rb['additional_label_simulations']>0
assert ra['simulations']==rb['simulations']-rb['additional_label_simulations']
assert ra['inference_calls']==rb['inference_calls']-rb['additional_label_inference_calls']
result=dict(games=16,rows=len(a),baseline_sha256=hashlib.sha256(prefix).hexdigest(),ensemble_sha256=hashlib.sha256((p/'4.bin').read_bytes()).hexdigest(),model_sha256=hashlib.sha256((ROOT/'research/e56/model/model.bin').read_bytes()).hexdigest(),baseline_matches_original_e58=True,same_trajectories_inputs_masks_outcomes=True,ensemble_labels_valid_and_different=True,primary_work_identical=True,additional_label_simulations=rb['additional_label_simulations'],mean_label_tv=float(.5*np.abs(a['policy']-b['policy']).sum(1).mean()))
(out/'ensemble-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
