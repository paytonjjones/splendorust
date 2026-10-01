import sys,json,torch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from attention_model import AttentionResidual,export
from flywheel_model import sha
parent=ROOT/'research/e88/model';model=AttentionResidual(parent/'model.pt');dest=ROOT/'local/research/e89/check.bin';export(model,dest)
assert sha(dest)==sha(parent/'model.bin'),'continued checkpoint does not reproduce native parent'
assert all(not p.requires_grad for p in model.base.parameters())
expected=torch.load(ROOT/'research/e81/model/model.pt',map_location='cpu',weights_only=True)['state_dict']
assert all(torch.equal(v,expected[k]) for k,v in model.base.state_dict().items())
result=dict(continued_native_export_exact=True,parent_sha256=sha(dest),frozen_base_exact=True,trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad))
(Path(__file__).parent/'warmstart-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
