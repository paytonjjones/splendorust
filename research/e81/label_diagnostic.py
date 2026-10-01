import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
old=ROOT/'local/research/e74/train/000000.bin';new=ROOT/'local/research/e81/train/000000.bin'
a=np.memmap(new,dtype=DTYPE,mode='r');b=np.memmap(old,dtype=DTYPE,mode='r');assert len(a)==len(b)
for k in ['setup','x','mask','outcome']:assert np.array_equal(a[k],b[k],equal_nan=True)
chosen=a['policy'].argmax(axis=1);prior=b['policy'][np.arange(len(a)),chosen]
result=dict(rows=len(a),chosen_action_agrees_old_policy_argmax=float(np.mean(chosen==b['policy'].argmax(axis=1))),old_policy_mass_on_new_verified_action=float(prior.mean()),old_policy_mass_below_01=float(np.mean(prior<.1)),old_policy_mass_below_001=float(np.mean(prior<.01)),value_credit_mean_absolute_difference=float(np.nanmean(np.abs(a['teacher']-b['teacher']))),old_sha256=sha(old),new_sha256=sha(new),scope='Identical first1000 E74 actor games. Verified noise0 chosen actions versus old noisy completed-Q targets; both teacher noise and target construction differ by design. Not a causal isolation of either change or a strength estimate.')
(ROOT/'research/e81/label-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
