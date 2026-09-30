#!/usr/bin/env python3
"""Bounded-memory bootstrap refinement from native self-play search targets."""
import argparse,json,time,os
from pathlib import Path
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','4')
import numpy as np
import torch
from flywheel_model import bootstrap,raw,export,open_rows,check_rows,sha

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--train',nargs='+',required=True);p.add_argument('--dev',nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--warmstart')
    p.add_argument('--epochs',type=int,default=10);p.add_argument('--batch-size',type=int,default=1024)
    p.add_argument('--device',default='mps');p.add_argument('--seed',type=int,default=800000007)
    p.add_argument('--selection',choices=['outcome','teacher','distillation'],default='outcome')
    p.add_argument('--trained-only',action='store_true')
    p.add_argument('--architecture',choices=['bootstrap','gated'],default='bootstrap')
    p.add_argument('--learning-rate',type=float,default=1e-4)
    p.add_argument('--bitplanes',action='store_true')
    p.add_argument('--distill-teacher')
    a=p.parse_args()
    if a.selection=='distillation' and not a.distill_teacher:p.error('distillation selection requires --distill-teacher')
    a.output.mkdir(parents=True,exist_ok=False)
    torch.manual_seed(a.seed);rng=np.random.default_rng(a.seed);torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True,warn_only=True)
    train,tids,tfiles=open_rows(a.train);dev,dids,dfiles=open_rows(a.dev)
    assert not tids & dids,'train/development setup overlap'
    for r in train+dev: check_rows(r)
    if a.architecture=='gated':
        from gated_model import Gated,export as native_export
        model=Gated(bitplanes=a.bitplanes)
        if a.warmstart:
            model.load_state_dict(torch.load(a.warmstart,map_location='cpu',weights_only=True)['state_dict'],strict=True)
        forward=lambda model,x:model(x)
    else:
        model=bootstrap(a.warmstart)
        forward=raw;native_export=export
    model=model.to(a.device)
    teacher_model=bootstrap(a.distill_teacher).to(a.device).eval() if a.distill_teacher else None
    optimizer=torch.optim.AdamW(model.parameters(),lr=a.learning_rate,weight_decay=1e-4)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=a.epochs,eta_min=a.learning_rate/10)
    def tensors(b):
        return [torch.from_numpy(np.array(b[k],copy=True)).to(a.device) for k in ['x','mask','policy','teacher','outcome']]
    def loss(b):
        x,mask,policy,teacher,outcome=tensors(b);logits,values=forward(model,x)
        logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
        pl=-(policy*logp).sum(-1).mean()
        ht=torch.isfinite(teacher);ho=torch.isfinite(outcome);valid=ht|ho
        target=torch.where(ht,torch.where(ho,0.5*torch.nan_to_num(outcome)+0.5*teacher,teacher),outcome)
        target=2*target[valid]-1
        vl=((values[valid,0]-target)**2+(values[valid,1]+target)**2).mean()/2 if valid.any() else values.sum()*0
        if teacher_model is not None:
            with torch.no_grad(): tl,tv=raw(teacher_model,x);tp=tl.masked_fill(mask==0,-1e9).softmax(-1)
            dl=-(tp*logp).sum(-1).mean()+((values-tv)**2).mean()
            return 0.2*(pl+vl)+0.8*dl
        return pl+vl
    def evaluate():
        model.eval();tot=np.zeros(6);n=0;nv=0;nt=0
        with torch.no_grad():
            for r in dev:
                for i in range(0,len(r),a.batch_size):
                    b=r[i:i+a.batch_size];x,mask,policy,teacher,outcome=tensors(b)
                    logits,v=forward(model,x);logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
                    tot[0]+=-(policy*logp).sum().item();tot[1]+=(logp.argmax(-1)==policy.argmax(-1)).sum().item()
                    valid=torch.isfinite(outcome);prob=(v[:,0]+1)/2
                    tot[2]+=((prob[valid]-outcome[valid])**2).sum().item();nv+=valid.sum().item();n+=len(b)
                    if teacher_model is not None:
                        tl,tv=raw(teacher_model,x);tlp=tl.masked_fill(mask==0,-1e9).log_softmax(-1)
                        tot[4]+=(tlp.exp()*(tlp-logp)).sum().item()
                        tot[5]+=((v-tv)**2).mean(-1).sum().item()
                    ht=torch.isfinite(teacher);tv=ht|valid
                    target=torch.where(ht,torch.where(valid,0.5*torch.nan_to_num(outcome)+0.5*teacher,teacher),outcome)
                    tot[3]+=((prob[tv]-target[tv])**2).sum().item();nt+=tv.sum().item()
        assert n>0 and nv>0
        return dict(policy_loss=tot[0]/n,policy_accuracy=tot[1]/n,value_brier=tot[2]/nv,teacher_target_brier=tot[3]/nt,rows=n,outcome_rows=int(nv),distillation_policy_kl=tot[4]/n if teacher_model is not None else None,distillation_value_mse=tot[5]/n if teacher_model is not None else None)
    start=time.monotonic();history=[];best=float('inf');best_epoch=0
    initial=evaluate();print(json.dumps(dict(stage='initial',**initial)),flush=True)
    # Keep the unchanged incumbent if all trained epochs reduce held-out quality.
    def save(epoch):
        torch.save({'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'epoch':epoch,'seed':a.seed,'architecture':a.architecture},a.output/'model.pt')
    metric='teacher_target_brier' if a.selection=='teacher' else 'value_brier'
    def score_for(metrics):
        return metrics['distillation_policy_kl']+4*metrics['distillation_value_mse'] if a.selection=='distillation' else metrics['policy_loss']+4*metrics[metric]
    initial_score=score_for(initial);best=initial_score;save(0)
    import shutil
    shutil.copy2(a.output/'model.pt',a.output/'epoch-zero.pt')
    if a.trained_only: best=float('inf')
    for epoch in range(1,a.epochs+1):
        model.train();trained=0
        # Each epoch visits every row once. Shuffle shards and rows; memory is O(shard rows + batch).
        for j in rng.permutation(len(train)):
            r=train[j];order=rng.permutation(len(r))
            for i in range(0,len(r),a.batch_size):
                b=r[order[i:i+a.batch_size]];optimizer.zero_grad(set_to_none=True)
                l=loss(b);assert torch.isfinite(l).item(),'nonfinite training loss'
                l.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step();trained+=len(b)
        scheduler.step();metrics=evaluate();metrics.update(epoch=epoch,seconds=time.monotonic()-start,trained_rows=trained)
        history.append(metrics);print(json.dumps(metrics),flush=True)
        score=score_for(metrics)
        if score<best: best=score;best_epoch=epoch;save(epoch)
    model.load_state_dict(torch.load(a.output/'model.pt',map_location=a.device,weights_only=True)['state_dict']);model.cpu().eval()
    native_export(model,a.output/'model.bin')
    fixture=np.array(dev[0]['x'][:64],copy=True)
    with torch.no_grad(): logits,v=forward(model,torch.from_numpy(fixture))
    (a.output/'parity.json').write_text(json.dumps(dict(x=fixture.tolist(),logits=logits.tolist(),values=v.tolist())))
    manifest=dict(schema='flywheel-training-v1',architecture=80 if a.architecture=='bootstrap' else 'gated-rms-swiglu-192x3-v2' if a.bitplanes else 'gated-rms-swiglu-192x3-v1',distill_teacher_sha256=sha(a.distill_teacher) if a.distill_teacher else None,learning_rate=a.learning_rate,parameters=sum(v.numel() for v in model.parameters()),
        seed=a.seed,device=a.device,torch=torch.__version__,numpy=np.__version__,train=tfiles,dev=dfiles,
        train_setups=len(tids),dev_setups=len(dids),warmstart_sha256=sha(a.warmstart) if a.warmstart else None,
        model_sha256=sha(a.output/'model.bin'),checkpoint_sha256=sha(a.output/'model.pt'),script_sha256=sha(__file__),
        model_code_sha256=sha(Path(__file__).with_name('flywheel_model.py')),gated_code_sha256=sha(Path(__file__).with_name('gated_model.py')) if a.architecture=='gated' else None,initial=initial,history=history,
        best_epoch=best_epoch,selection=f'minimum dev {a.selection} score; trained_only={a.trained_only}',initial_score=initial_score,trained_only=a.trained_only,
        seconds=time.monotonic()-start,epochs=a.epochs,batch_size=a.batch_size,
        determinism='fixed seeds; deterministic algorithms requested; MPS bitwise repeatability not guaranteed')
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
