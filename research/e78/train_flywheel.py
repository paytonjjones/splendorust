#!/usr/bin/env python3
"""Bounded-memory bootstrap refinement from native self-play search targets."""
import argparse,json,time,os
from pathlib import Path
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','4')
import numpy as np
import torch
from flywheel_model import bootstrap,raw,export,open_rows,check_rows,sha

def greedy_visit_targets(x, policy):
    """Keep opening exploration; share late target mass across maximal visits."""
    maxima=(policy==policy.max(dim=-1,keepdim=True).values).to(policy.dtype)
    greedy=maxima/maxima.sum(dim=-1,keepdim=True)
    return torch.where((x[:,6]>=6).unsqueeze(-1),greedy,policy)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--train',nargs='+',required=True);p.add_argument('--dev',nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--warmstart')
    p.add_argument('--epochs',type=int,default=10);p.add_argument('--batch-size',type=int,default=1024)
    p.add_argument('--device',default='mps');p.add_argument('--seed',type=int,default=800000007)
    p.add_argument('--selection',choices=['outcome','teacher','distillation'],default='outcome')
    p.add_argument('--trained-only',action='store_true')
    p.add_argument('--architecture',choices=['bootstrap','gated','split-bootstrap','residual'],default='bootstrap')
    p.add_argument('--learning-rate',type=float,default=1e-4)
    p.add_argument('--bitplanes',action='store_true')
    p.add_argument('--residual-width',type=int,default=192)
    p.add_argument('--residual-blocks',type=int,default=3)
    p.add_argument('--public-context',action='store_true')
    p.add_argument('--distill-teacher')
    p.add_argument('--trunk-blocks',type=int)
    p.add_argument('--policy-only',action='store_true')
    p.add_argument('--greedy-targets',action='store_true')
    p.add_argument('--sample-encoding-views',action='store_true')
    a=p.parse_args()
    if a.warmstart and torch.load(a.warmstart,map_location='cpu',weights_only=True).get('input_rows',56)==57:a.public_context=True
    if a.public_context and (a.architecture!='bootstrap' or a.policy_only or a.distill_teacher):p.error('public context requires full bootstrap training')
    if not (32<=a.residual_width<=512 and a.residual_width%8==0 and 1<=a.residual_blocks<=8):p.error('residual dimensions require width 32..512 in multiples of eight and blocks 1..8')
    if a.architecture=='residual' and not a.warmstart:p.error('residual requires a learned base checkpoint')
    if a.trunk_blocks is not None and a.architecture!='bootstrap':p.error('trunk-blocks requires bootstrap')
    if a.policy_only and a.architecture!='bootstrap':p.error('policy-only requires the bootstrap architecture')
    if a.policy_only and a.distill_teacher:p.error('policy-only uses root policy targets; do not combine with distillation')
    if a.selection=='distillation' and not a.distill_teacher:p.error('distillation selection requires --distill-teacher')
    a.output.mkdir(parents=True,exist_ok=False)
    torch.manual_seed(a.seed);rng=np.random.default_rng(a.seed);torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True,warn_only=True)
    train,tids,tfiles=open_rows(a.train);dev,dids,dfiles=open_rows(a.dev)
    assert not tids & dids,'train/development setup overlap'
    for r in train+dev: check_rows(r)
    def context_files(paths,rows):
        groups=[];files=[]
        for name,r in zip(paths,rows):
            path=Path(name).with_suffix('.context.bin');assert path.stat().st_size==len(r)*28
            c=np.memmap(path,mode='r',dtype='<f4',shape=(len(r),7));assert np.isfinite(c).all() and ((c>=0)&(c<=1)).all()
            groups.append(c);files.append(dict(path=str(path),sha256=sha(path)))
        return groups,files
    if a.public_context:
        train_context,train_context_files=context_files(a.train,train)
        dev_context,dev_context_files=context_files(a.dev,dev)
    view_files=None
    if a.sample_encoding_views:
        from encoding_views import open_views,sample_views
        view_groups,view_files=open_views(a.train,train)
        augmentation_rng=np.random.default_rng(a.seed ^ 0x6a09e667)
    if a.architecture=='residual':
        from residual_model import Residual,export as export_residual
        model=Residual(a.warmstart,a.residual_width,a.residual_blocks);forward=lambda model,x:model(x);native_export=export_residual
        base_state={k:v.clone() for k,v in model.base.state_dict().items()}
    elif a.architecture=='split-bootstrap':
        from split_model import SplitBootstrap,export_split
        model=SplitBootstrap(a.warmstart)
        forward=lambda model,x:model(x)
        native_export=export_split
    elif a.architecture=='gated':
        from gated_model import Gated,load_state,export as native_export
        model=Gated(bitplanes=a.bitplanes)
        if a.warmstart:
            load_state(model,a.warmstart)
        forward=lambda model,x:model(x)
    else:
        model=bootstrap(a.warmstart)
        if a.public_context:
            from flywheel_model import expand_inputs
            expand_inputs(model,57)
        from flywheel_model import expand_trunk
        if a.trunk_blocks is None:a.trunk_blocks=len(model.trunk)
        expand_trunk(model,a.trunk_blocks)
        forward=raw;native_export=export
    if a.policy_only:
        for name,param in model.named_parameters():param.requires_grad_(name.startswith('output_layers_PI.'))
        assert any(p.requires_grad for p in model.parameters()),'missing trainable policy head'
    model=model.to(a.device)
    teacher_model=None;teacher_forward=raw
    if a.distill_teacher:
        payload=torch.load(a.distill_teacher,map_location='cpu',weights_only=True)
        if payload.get('architecture')=='residual':
            from residual_model import Residual
            teacher_model=Residual(a.distill_teacher)
            teacher_forward=lambda model,x:model(x)
        elif payload.get('architecture')=='split-bootstrap':
            from split_model import SplitBootstrap
            teacher_model=SplitBootstrap(a.distill_teacher)
            teacher_forward=lambda model,x:model(x)
        elif payload.get('architecture')=='gated':
            from gated_model import Gated,load_state
            width,inputs=payload['state_dict']['stem.weight'].shape
            blocks=1+max(int(k.split('.')[1]) for k in payload['state_dict'] if k.startswith('blocks.'))
            teacher_model=load_state(Gated(width,blocks,bitplanes=inputs==512),a.distill_teacher)
            teacher_forward=lambda model,x:model(x)
        else:teacher_model=bootstrap(a.distill_teacher)
        teacher_model=teacher_model.to(a.device).eval()
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=a.learning_rate,weight_decay=1e-4)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=a.epochs,eta_min=a.learning_rate/10)
    def tensors(b,context=None):
        values=[torch.from_numpy(np.array(b[k],copy=True)).to(a.device) for k in ['x','mask','policy','teacher','outcome']]
        if context is not None:values[0]=torch.cat([values[0],torch.from_numpy(np.array(context,copy=True)).to(a.device)],dim=-1)
        if a.greedy_targets:values[2]=greedy_visit_targets(values[0],values[2])
        return values
    def loss(b,context=None):
        x,mask,policy,teacher,outcome=tensors(b,context);logits,values=forward(model,x)
        logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
        pl=-(policy*logp).sum(-1).mean()
        ht=torch.isfinite(teacher);ho=torch.isfinite(outcome);valid=ht|ho
        target=torch.where(ht,torch.where(ho,0.5*torch.nan_to_num(outcome)+0.5*teacher,teacher),outcome)
        target=2*target[valid]-1
        vl=((values[valid,0]-target)**2+(values[valid,1]+target)**2).mean()/2 if valid.any() else values.sum()*0
        if a.policy_only:return pl
        if teacher_model is not None:
            with torch.no_grad(): tl,tv=teacher_forward(teacher_model,x);tp=tl.masked_fill(mask==0,-1e9).softmax(-1)
            dl=-(tp*logp).sum(-1).mean()+((values-tv)**2).mean()
            return 0.2*(pl+vl)+0.8*dl
        return pl+vl
    def evaluate():
        model.eval();tot=np.zeros(6);n=0;nv=0;nt=0
        with torch.no_grad():
            for dev_index,r in enumerate(dev):
                for i in range(0,len(r),a.batch_size):
                    b=r[i:i+a.batch_size];x,mask,policy,teacher,outcome=tensors(b,dev_context[dev_index][i:i+a.batch_size] if a.public_context else None)
                    logits,v=forward(model,x);logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1)
                    tot[0]+=-(policy*logp).sum().item();tot[1]+=(logp.argmax(-1)==policy.argmax(-1)).sum().item()
                    valid=torch.isfinite(outcome);prob=(v[:,0]+1)/2
                    tot[2]+=((prob[valid]-outcome[valid])**2).sum().item();nv+=valid.sum().item();n+=len(b)
                    if teacher_model is not None:
                        tl,tv=teacher_forward(teacher_model,x);tlp=tl.masked_fill(mask==0,-1e9).log_softmax(-1)
                        tot[4]+=(tlp.exp()*(tlp-logp)).sum().item()
                        tot[5]+=((v-tv)**2).mean(-1).sum().item()
                    ht=torch.isfinite(teacher);tv=ht|valid
                    target=torch.where(ht,torch.where(valid,0.5*torch.nan_to_num(outcome)+0.5*teacher,teacher),outcome)
                    tot[3]+=((prob[tv]-target[tv])**2).sum().item();nt+=tv.sum().item()
        assert n>0 and nv>0
        return dict(policy_loss=tot[0]/n,policy_accuracy=tot[1]/n,value_brier=tot[2]/nv,teacher_target_brier=tot[3]/nt,rows=n,outcome_rows=int(nv),distillation_policy_kl=tot[4]/n if teacher_model is not None else None,distillation_value_mse=tot[5]/n if teacher_model is not None else None)
    fixed_values=None
    if a.policy_only or a.architecture=='split-bootstrap':
        import copy
        frozen=copy.deepcopy(model).cpu().eval()
        with torch.no_grad():fixed_values=forward(frozen,torch.from_numpy(np.array(dev[0]['x'][:64],copy=True)))[1]
        del frozen
    start=time.monotonic();history=[];best=float('inf');best_epoch=0
    initial=evaluate();print(json.dumps(dict(stage='initial',**initial)),flush=True)
    # Keep the unchanged incumbent if all trained epochs reduce held-out quality.
    def save(epoch):
        torch.save({'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'epoch':epoch,'seed':a.seed,'architecture':a.architecture,'input_rows':getattr(model,'input_rows',56),'trunk_blocks':a.trunk_blocks if a.architecture=='bootstrap' else None,'policy_trunk_blocks':len(model.policy.trunk) if a.architecture=='split-bootstrap' else None,'critic_trunk_blocks':len(model.critic.trunk) if a.architecture=='split-bootstrap' else None,**(model.metadata() if a.architecture=='residual' else {})},a.output/'model.pt')
    metric='teacher_target_brier' if a.selection=='teacher' else 'value_brier'
    def score_for(metrics):
        return metrics['distillation_policy_kl']+4*metrics['distillation_value_mse'] if a.selection=='distillation' else metrics['policy_loss']+4*metrics[metric]
    initial_score=score_for(initial);best=initial_score;save(0)
    import shutil
    shutil.copy2(a.output/'model.pt',a.output/'epoch-zero.pt')
    if a.trained_only: best=float('inf')
    for epoch in range(1,a.epochs+1):
        model.train();trained=0
        if a.policy_only:
            # Gradients alone do not freeze running mean/variance.
            model.first_layer.eval();model.trunk.eval();model.output_layers_V.eval()
        # Each epoch visits every row once. Shuffle shards and rows; memory is O(shard rows + batch).
        for j in rng.permutation(len(train)):
            r=train[j];order=rng.permutation(len(r))
            for i in range(0,len(r),a.batch_size):
                indices=order[i:i+a.batch_size];b=np.array(r[indices],copy=True)
                if a.sample_encoding_views:b['x']=sample_views(b['x'],indices,view_groups[j],augmentation_rng)
                optimizer.zero_grad(set_to_none=True)
                l=loss(b,train_context[j][indices] if a.public_context else None);assert torch.isfinite(l).item(),'nonfinite training loss'
                l.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step();trained+=len(b)
        scheduler.step();metrics=evaluate();metrics.update(epoch=epoch,seconds=time.monotonic()-start,trained_rows=trained)
        history.append(metrics);print(json.dumps(metrics),flush=True)
        score=score_for(metrics)
        if score<best: best=score;best_epoch=epoch;save(epoch)
    if a.architecture=='gated':load_state(model,a.output/'model.pt',a.device)
    else:model.load_state_dict(torch.load(a.output/'model.pt',map_location=a.device,weights_only=True)['state_dict'])
    model.cpu().eval()
    if a.architecture=='residual':assert all(torch.equal(v,model.base.state_dict()[k]) for k,v in base_state.items()),'fixed base changed'
    native_export(model,a.output/'model.bin')
    fixture=np.array(dev[0]['x'][:64],copy=True)
    fixture_context=np.array(dev_context[0][:64],copy=True) if a.public_context else None
    model_input=torch.from_numpy(np.concatenate([fixture,fixture_context],axis=-1) if a.public_context else fixture)
    with torch.no_grad(): logits,v=forward(model,model_input)
    if fixed_values is not None:assert torch.equal(fixed_values,v),'frozen critic changed'
    (a.output/'parity.json').write_text(json.dumps(dict(x=fixture.tolist(),context=fixture_context.tolist() if a.public_context else None,logits=logits.tolist(),values=v.tolist())))
    manifest=dict(schema='flywheel-training-v1',input_rows=getattr(model,'input_rows',56),public_context=a.public_context,train_context_files=train_context_files if a.public_context else None,dev_context_files=dev_context_files if a.public_context else None,trunk_blocks=a.trunk_blocks if a.architecture=='bootstrap' else None,architecture=f'residual-rms-swiglu-{model.delta.width}x{model.delta.block_count}-v1' if a.architecture=='residual' else 80 if a.architecture=='bootstrap' else 'split-bootstrap' if a.architecture=='split-bootstrap' else 'gated-rms-swiglu-192x3-v2' if a.bitplanes else 'gated-rms-swiglu-192x3-v1',distill_teacher_sha256=sha(a.distill_teacher) if a.distill_teacher else None,learning_rate=a.learning_rate,parameters=sum(v.numel() for v in model.parameters()),
        sample_encoding_views=a.sample_encoding_views,encoding_views_files=view_files,encoding_views_code_sha256=sha(Path(__file__).with_name('encoding_views.py')) if a.sample_encoding_views else None,greedy_targets=a.greedy_targets,policy_only=a.policy_only,frozen_value_exact=torch.equal(fixed_values,v) if fixed_values is not None else None,trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad),seed=a.seed,device=a.device,torch=torch.__version__,numpy=np.__version__,train=tfiles,dev=dfiles,
        train_setups=len(tids),dev_setups=len(dids),warmstart_sha256=sha(a.warmstart) if a.warmstart else None,
        model_sha256=sha(a.output/'model.bin'),checkpoint_sha256=sha(a.output/'model.pt'),script_sha256=sha(__file__),
        split_code_sha256=sha(Path(__file__).with_name('split_model.py')) if a.architecture=='split-bootstrap' else None,model_code_sha256=sha(Path(__file__).with_name('flywheel_model.py')),gated_code_sha256=sha(Path(__file__).with_name('gated_model.py')) if a.architecture in ['gated','residual'] else None,residual_code_sha256=sha(Path(__file__).with_name('residual_model.py')) if a.architecture=='residual' else None,fixed_base_exact=True if a.architecture=='residual' else None,base_model_sha256=sha(a.output/'base.bin') if a.architecture=='residual' else None,initial=initial,history=history,
        best_epoch=best_epoch,selection=f'minimum dev {a.selection} score; trained_only={a.trained_only}',initial_score=initial_score,trained_only=a.trained_only,
        seconds=time.monotonic()-start,epochs=a.epochs,batch_size=a.batch_size,
        determinism='fixed seeds; deterministic algorithms requested; MPS bitwise repeatability not guaranteed')
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
