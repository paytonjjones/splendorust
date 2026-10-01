"""Held-out E87 target fit by public hidden-card status; no arena claim."""
import json,sys
from pathlib import Path
import numpy as np,torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from flywheel_model import DTYPE,raw
from attention_model import AttentionResidual
model=AttentionResidual(ROOT/'research/e88/model/model.pt').to('mps').eval()
p=ROOT/'local/research/e88/data/e87-dev.bin';rows=np.memmap(p,dtype=DTYPE,mode='r');ctx=np.memmap(p.with_suffix('.context.bin'),dtype='<f4',mode='r',shape=(len(rows),911))
sums={f'{kind}/{group}':np.zeros(4) for kind in ['sampled-base','mean-base','attention'] for group in ['all','blind','known']}
with torch.no_grad():
 for i in range(0,len(rows),1024):
  r=rows[i:i+1024];c=np.array(ctx[i:i+1024],copy=True);x=torch.from_numpy(np.array(r['x'],copy=True)).to('mps');ct=torch.from_numpy(c).to('mps');mask=torch.from_numpy(np.array(r['mask'],copy=True)).to('mps');policy=torch.from_numpy(np.array(r['policy'],copy=True)).to('mps');outcome=torch.from_numpy(np.array(r['outcome'],copy=True)).to('mps');groups={'all':np.ones(len(r),bool),'blind':c[:,-1]>0,'known':c[:,-1]==0}
  for kind,(pi,v) in [('sampled-base',raw(model.base,x)),('mean-base',raw(model.base,ct[:,:392])),('attention',model(torch.cat([x,ct],-1)))]:
   logp=pi.masked_fill(mask==0,-1e9).log_softmax(-1);ce=-(policy*logp).sum(-1).cpu().numpy();correct=(logp.argmax(-1)==policy.argmax(-1)).cpu().numpy();brier=(((v[:,0]+1)/2-outcome)**2).cpu().numpy()
   for group,g in groups.items():sums[f'{kind}/{group}']+=np.array([g.sum(),ce[g].sum(),correct[g].sum(),brier[g].sum()])
result={k:dict(rows=int(v[0]),policy_loss=v[1]/v[0],policy_accuracy=v[2]/v[0],outcome_brier=v[3]/v[0]) for k,v in sums.items()}
result['scope']='E87 development targets; E88 selected on this development set; descriptive fit, not independent strength evidence'
(Path(__file__).parent/'parent-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
