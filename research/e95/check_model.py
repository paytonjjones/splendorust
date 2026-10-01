"""Check zero expansion, checkpoint reload and native fixture for both rules."""
import sys,json
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from flywheel_model import DTYPE,bootstrap,raw,sha
from public_model import load,inputs,export
from public_features import batch
out=ROOT/'local/research/e95/model-validation';out.mkdir(exist_ok=False)
a=np.fromfile(ROOT/'local/research/e95/validation-serial/data.bin',dtype=DTYPE);ctx=np.fromfile(ROOT/'local/research/e95/validation-serial/data.context.bin',dtype='<f4').reshape(-1,7)
torch.set_num_threads(4);m=load(ROOT/'research/e81/model/model.pt').eval();old=bootstrap(ROOT/'research/e81/model/model.pt').eval();x=a['x'].copy();mean,_=batch(x,ctx);profiles=np.arange(len(x))%2
with torch.no_grad():
 expected=raw(old,torch.from_numpy(mean));actual=raw(m,torch.from_numpy(inputs(x,ctx,profiles)))
 for a1,b in zip(actual,expected):assert torch.equal(a1,b)
export(m,out/'model.bin');torch.save(dict(state_dict=m.state_dict(),input_rows=75,trunk_blocks=1),out/'model.pt');reloaded=load(out/'model.pt').eval()
with torch.no_grad():
 other=raw(reloaded,torch.from_numpy(inputs(x,ctx,profiles)))
 for a1,b in zip(actual,other):assert torch.equal(a1,b)
(out/'parity.json').write_text(json.dumps(dict(x=x.tolist(),context=ctx.tolist(),native_profiles=profiles.astype(bool).tolist(),logits=actual[0].tolist(),values=actual[1].tolist()))+'\n')
(ROOT/'research/e95/model-validation.json').write_text(json.dumps(dict(rows=len(x),blind_rows=int((ctx[:,:3].sum(-1)>0).sum()),zero_expansion_exact=True,checkpoint_reload_exact=True,parameters=sum(v.numel() for v in m.parameters()),model_sha256=sha(out/'model.bin'),scope='Initialization only; no trained model or strength claim'),indent=2)+'\n')
