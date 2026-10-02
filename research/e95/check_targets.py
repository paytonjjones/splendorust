"""Check the real canonical replay's missing helper-value targets."""
import sys,json
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from flywheel_model import DTYPE
from train import target_credit
missing=0;rows=0
for p in [ROOT/'local/research/e87/train/004000.bin',ROOT/'local/research/e87/dev.bin']:
 r=np.fromfile(p,dtype=DTYPE);teacher=torch.from_numpy(r['teacher'].copy()).to('mps');outcome=torch.from_numpy(r['outcome'].copy()).to('mps');target=target_credit(teacher,outcome);assert torch.isfinite(target).all()
 ht=torch.isfinite(teacher);assert torch.equal(target[~ht],outcome[~ht]);assert torch.equal(target[ht],((teacher+outcome)/2)[ht]);missing+=int((~ht).sum());rows+=len(r)
(ROOT/'research/e95/target-fallback.json').write_text(json.dumps(dict(canonical_rows=rows,missing_helper_teacher_values=missing,finite_target_fallback_to_outcome=True,valid_teacher_mixture_unchanged=True,scope='Real replay target validation; no model strength claim'),indent=2)+'\n')
