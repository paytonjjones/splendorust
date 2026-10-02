"""Train one public model on native expert data plus fixed canonical replay."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(Path(__file__).parent))
from flywheel_model import DTYPE,open_rows,check_rows,raw,sha
from public_model import load,export,inputs

def target_credit(teacher,outcome):
 assert torch.isfinite(outcome).all(), 'complete games require finite outcomes'
 return torch.where(torch.isfinite(teacher),(teacher+outcome)/2,outcome)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--epochs',type=int,default=10);args=ap.parse_args();out=args.output;out.mkdir(exist_ok=False,parents=True)
 seed=800000022;torch.manual_seed(seed);rng=np.random.default_rng(seed);torch.set_num_threads(4);torch.use_deterministic_algorithms(True,warn_only=True);device='mps';batch_size=1024;start=time.monotonic()
 native=ROOT/'local/research/e95';train_paths=sorted((native/'train').glob('*/data.bin'));dev_paths=sorted((native/'dev').glob('*/data.bin'));assert len(train_paths)==25 and len(dev_paths)==5
 train_paths.append(ROOT/'local/research/e87/train/004000.bin');dev_paths.append(ROOT/'local/research/e87/dev.bin')
 train,tids,tfiles=open_rows(train_paths);dev,dids,dfiles=open_rows(dev_paths);assert not tids&dids
 for rows in train+dev:check_rows(rows)
 def cache(paths,groups,split):
  result=[];receipts=[]
  for index,(path,rows) in enumerate(zip(paths,groups)):
   ctx=np.fromfile(path.with_suffix('.context.bin'),dtype='<f4').reshape(-1,7);assert len(ctx)==len(rows);is_native=path.is_relative_to(native)
   cache_dir=ROOT/'local/research/e95/model-input-cache';cache_dir.mkdir(exist_ok=True);dest=cache_dir/(split+'-'+('native-' if is_native else 'canonical-')+str(index)+'-'+str(len(rows))+'.inputs.bin')
   packed=np.memmap(dest,mode='w+',dtype='<f4',shape=(len(rows),525))
   for i in range(0,len(rows),2048):packed[i:i+2048]=inputs(rows['x'][i:i+2048],ctx[i:i+2048],is_native)
   packed.flush();assert np.isfinite(packed).all();result.append((packed,is_native,ctx));receipts.append(dict(source=str(path),context_sha256=sha(path.with_suffix('.context.bin')),inputs_sha256=sha(dest),native_rules=is_native,rows=len(rows)))
  return result,receipts
 tr,tc=cache(train_paths,train,'train');dv,dc=cache(dev_paths,dev,'dev');(out/'input-receipts.json').write_text(json.dumps(dict(train=tc,dev=dc),indent=2)+'\n')
 model=load(ROOT/'research/e81/model/model.pt').to(device);opt=torch.optim.AdamW(model.parameters(),lr=1e-4,weight_decay=1e-4);scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=args.epochs,eta_min=1e-5)
 def tensors(rows,x):return [torch.from_numpy(np.array(v,copy=True)).to(device) for v in [x,rows['mask'],rows['policy'],rows['teacher'],rows['outcome']]]
 def evaluate():
  model.eval();sums={k:np.zeros(5) for k in ['native','canonical']}
  with torch.no_grad():
   for r,(x,native_rules,_) in zip(dev,dv):
    total=sums['native' if native_rules else 'canonical']
    for i in range(0,len(r),batch_size):
     xx,mask,policy,teacher,outcome=tensors(r[i:i+batch_size],x[i:i+batch_size]);logits,v=raw(model,xx);logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1);prob=(v[:,0]+1)/2
     total+=np.array([-(policy*logp).sum().item(),(logp.argmax(-1)==policy.argmax(-1)).sum().item(),((prob-outcome)**2).sum().item(),((prob-target_credit(teacher,outcome))**2).sum().item(),len(xx)])
  metrics={k:dict(policy_loss=v[0]/v[4],policy_accuracy=v[1]/v[4],value_brier=v[2]/v[4],teacher_brier=v[3]/v[4],rows=int(v[4])) for k,v in sums.items()};total=sum(sums.values());metrics['selection_score']=(total[0]+4*total[2])/total[4];return metrics
 def save(epoch):torch.save(dict(state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()},input_rows=75,trunk_blocks=1,architecture='bootstrap-public-75-v1',epoch=epoch,seed=seed),out/'model.pt')
 initial=evaluate();best=initial['selection_score'];best_epoch=0;save(0);history=[];print(json.dumps(dict(stage='initial',**initial)),flush=True)
 for epoch in range(1,args.epochs+1):
  model.train();trained=0
  for j in rng.permutation(len(train)):
   r=train[j];x=tr[j][0];order=rng.permutation(len(r))
   for i in range(0,len(r),batch_size):
    ix=order[i:i+batch_size];xx,mask,policy,teacher,outcome=tensors(r[ix],x[ix]);logits,v=raw(model,xx);logp=logits.masked_fill(mask==0,-1e9).log_softmax(-1);target=2*target_credit(teacher,outcome)-1
    loss=-(policy*logp).sum(-1).mean()+((v[:,0]-target)**2+(v[:,1]+target)**2).mean()/2
    assert torch.isfinite(loss);opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step();trained+=len(ix)
  scheduler.step();m=evaluate();m.update(epoch=epoch,seconds=time.monotonic()-start,trained_rows=trained);history.append(m);print(json.dumps(m),flush=True)
  if m['selection_score']<best:best=m['selection_score'];best_epoch=epoch;save(epoch)
 model=load(out/'model.pt').eval();export(model,out/'model.bin');fixture=[];contexts=[];profiles=[]
 for r,(_,native_rules,ctx) in zip(dev,dv):fixture.extend(r['x'][:16]);contexts.extend(ctx[:16]);profiles.extend([native_rules]*min(16,len(r)))
 x=np.asarray(fixture,dtype='<f4');c=np.asarray(contexts,dtype='<f4')
 with torch.no_grad():pi,v=raw(model,torch.from_numpy(inputs(x,c,np.asarray(profiles))))
 (out/'parity.json').write_text(json.dumps(dict(x=x.tolist(),context=c.tolist(),native_profiles=profiles,logits=pi.tolist(),values=v.tolist()))+'\n')
 manifest=dict(schema='public-external-teacher-training-v1',architecture='bootstrap-public-75-v1',input_rows=75,profile_index=519,parameters=sum(p.numel() for p in model.parameters()),seed=seed,epochs=args.epochs,batch_size=batch_size,learning_rate=1e-4,train=tfiles,dev=dfiles,train_setups=len(tids),dev_setups=len(dids),initial=initial,history=history,best_epoch=best_epoch,seconds=time.monotonic()-start,model_sha256=sha(out/'model.bin'),checkpoint_sha256=sha(out/'model.pt'),scripts={str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name('public_model.py'),ROOT/'research/e86/public_features.py']},selection='Combined dev policy CE +4 outcome Brier; native and canonical metrics separate',determinism='Fixed seeds; deterministic algorithms requested; MPS bitwise repeatability not guaranteed')
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
