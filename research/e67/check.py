"""Check compatibility and independence of student-trajectory collection."""
import sys,json,shutil
from pathlib import Path
sys.path.insert(0,str(Path('research').resolve()))
import numpy as np
from flywheel_model import DTYPE,sha,check_rows
OUT=Path('research/e67');LOCAL=Path('local/research/e67')
def rows(name):return np.memmap(LOCAL/(name+'.bin'),mode='r',dtype=DTYPE)
def same_states(a,b):
 assert len(a)==len(b)
 for key in ['setup','x','mask','outcome']:assert np.array_equal(a[key],b[key],equal_nan=True),key
old=np.memmap('local/research/e64/train.bin',mode='r',dtype=DTYPE);default=rows('default')
assert default.tobytes()==old[:len(default)].tobytes()
equal=rows('equal');student=rows('student');changed=rows('changed-teacher');serial=rows('serial')
same_states(default,equal);same_states(student,changed)
assert student.tobytes()==serial.tobytes()
assert not np.array_equal(student['policy'],changed['policy'])
assert not np.array_equal(default['x'],student['x'])
for name in ['default','equal','student','changed-teacher','serial']:
 r=rows(name);check_rows(r);m=json.loads((LOCAL/(name+'.json')).read_text())
 assert m['rows']==len(r) and m['blocked']==0 and m['capped']==0
 if m['separate_actor']:
  assert m['additional_label_simulations']>0
  assert m['simulations']>m['additional_label_simulations']
 shutil.copy2(LOCAL/(name+'.json'),OUT/(name+'.json'))
result=dict(default_matches_prior_raw=True,same_budget_actor_state_parity=True,teacher_budget_does_not_change_actor_states=True,serial_parallel_exact=True,labels_legal=True,work_counts_separate=True,default_rows=len(default),student_rows=len(student),hashes={name:sha(LOCAL/(name+'.bin')) for name in ['default','equal','student','changed-teacher','serial']})
(OUT/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
