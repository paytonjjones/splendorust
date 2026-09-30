"""Measure train/dev target fit without changing the teacher or student."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
import torch
from flywheel_model import bootstrap,raw,open_rows,sha

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--train',nargs='+',required=True);p.add_argument('--dev',nargs='+',required=True)
    p.add_argument('--checkpoint',required=True);p.add_argument('--output',required=True)
    p.add_argument('--device',default='mps');a=p.parse_args();torch.set_num_threads(2)
    train,ts,tf=open_rows(a.train);dev,ds,df=open_rows(a.dev);assert not ts&ds
    model=bootstrap(a.checkpoint).to(a.device).eval();start=time.monotonic()
    def evaluate(shards):
        total=np.zeros(7);count=0;valid_outcomes=0
        with torch.no_grad():
            for r in shards:
                for i in range(0,len(r),1024):
                    b=r[i:i+1024];x=torch.from_numpy(np.array(b['x'],copy=True)).to(a.device)
                    mask=torch.from_numpy(np.array(b['mask'],copy=True)).to(a.device)
                    target=torch.from_numpy(np.array(b['policy'],copy=True)).to(a.device)
                    assert torch.isfinite(target).all() and torch.allclose(target.sum(-1),torch.ones(len(b),device=a.device),atol=1e-5)
                    logits,value=raw(model,x);lp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
                    entropy=-(target*target.clamp_min(1e-30).log()).sum(-1)
                    ce=-(target*lp).sum(-1);chosen=lp.argmax(-1)
                    max_target=target.max(-1).values;greedy_target=target.gather(1,chosen[:,None])[:,0]
                    prob=(value[:,0]+1)/2
                    outcome=torch.from_numpy(np.array(b['outcome'],copy=True)).to(a.device);valid=torch.isfinite(outcome)
                    total+=np.array([ce.sum().item(),entropy.sum().item(),(chosen==target.argmax(-1)).sum().item(),max_target.sum().item(),greedy_target.sum().item(),((prob[valid]-outcome[valid])**2).sum().item(),(lp.exp()-target).abs().sum().item()/2])
                    count+=len(b);valid_outcomes+=valid.sum().item()
        return dict(rows=count,policy_ce=total[0]/count,target_entropy=total[1]/count,policy_kl=(total[0]-total[1])/count,argmax_agreement=total[2]/count,target_max_probability=total[3]/count,target_probability_of_student_argmax=total[4]/count,value_brier=total[5]/valid_outcomes,mean_policy_tv=total[6]/count)
    result=dict(schema='distillation-fit-diagnostic-v1',checkpoint_sha256=sha(a.checkpoint),script_sha256=sha(__file__),train_files=tf,dev_files=df,train=evaluate(train),dev=evaluate(dev),device=a.device,scope='Policy/label fit on observation encodings. A small train/dev gap alone does not distinguish capacity, optimization, or target ambiguity.')
    result['seconds']=time.monotonic()-start;Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['train','dev','seconds']}))
if __name__=='__main__':main()
