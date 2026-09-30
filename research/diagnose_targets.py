#!/usr/bin/env python3
"""Prediction diagnostics only; never use these scores as playing promotion evidence."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from flywheel_model import bootstrap,raw,open_rows

def main():
    p=argparse.ArgumentParser();p.add_argument('cycle',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='mps');a=p.parse_args()
    rows,_,_=open_rows(sorted((a.cycle/'dev').glob('*.bin')))
    torch.set_num_threads(4)
    models={'bootstrap':bootstrap().eval().to(a.device),'trained':bootstrap(a.cycle/'model/model.pt').eval().to(a.device)}
    totals={stage:dict(rows=0,entropy=0.,teacher_brier=0.,outcomes=0,bootstrap_ce=0.,trained_ce=0.,bootstrap_brier=0.,trained_brier=0.) for stage in ['all','opening','middle','late']}
    with torch.no_grad():
        for r in rows:
            for start in range(0,len(r),4096):
                b=r[start:start+4096];x=torch.from_numpy(np.array(b['x'],copy=True)).to(a.device)
                mask=torch.from_numpy(np.array(b['mask'],copy=True)).to(a.device)
                policy=torch.from_numpy(np.array(b['policy'],copy=True)).to(a.device)
                outputs={}
                for name,m in models.items():
                    logits,v=raw(m,x);logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
                    outputs[name]=(-(policy*logp).sum(-1).cpu().numpy(),((v[:,0]+1)/2).cpu().numpy())
                target=b['policy'];entropy=-(target*np.log(np.maximum(target,1e-30))).sum(-1)
                for stage,select in [('all',np.ones(len(b),dtype=bool)),('opening',b['x'][:,6]<16),('middle',(b['x'][:,6]>=16)&(b['x'][:,6]<40)),('late',b['x'][:,6]>=40)]:
                    t=totals[stage];t['rows']+=int(select.sum());t['entropy']+=float(entropy[select].sum())
                    valid=select&np.isfinite(b['outcome']);t['outcomes']+=int(valid.sum())
                    teacher=valid&np.isfinite(b['teacher'])
                    t.setdefault('teacher_outcomes',0);t['teacher_outcomes']+=int(teacher.sum())
                    t['teacher_brier']+=float(((b['teacher'][teacher]-b['outcome'][teacher])**2).sum())
                    for name,(ce,prob) in outputs.items():
                        t[name+'_ce']+=float(ce[select].sum());t[name+'_brier']+=float(((prob[valid]-b['outcome'][valid])**2).sum())
    for t in totals.values():
        for key in ['entropy','bootstrap_ce','trained_ce']:t[key]/=t['rows']
        t['teacher_brier']/=t['teacher_outcomes']
        for name in models:
            t[name+'_brier']/=t['outcomes'];t[name+'_kl']=t[name+'_ce']-t['entropy']
    a.output.write_text(json.dumps(dict(stages=totals,scope='Held-out position-weighted prediction scores, correlated within games; does not establish playing strength or identify capacity from loss alone.'),indent=2)+'\n')
if __name__=='__main__':main()
