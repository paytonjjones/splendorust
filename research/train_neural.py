#!/usr/bin/env python3
"""Residual policy/value distillation. Independent setup files; missing values masked."""
import argparse,hashlib,json,os,time
from pathlib import Path
os.environ['VECLIB_MAXIMUM_THREADS']='4'
import numpy as np
import torch
from torch import nn
p=argparse.ArgumentParser();p.add_argument('train');p.add_argument('dev');p.add_argument('output');p.add_argument('--epochs',type=int,default=20);p.add_argument('--device',default='mps');a=p.parse_args()
torch.manual_seed(250000007);np.random.seed(250000007);torch.set_num_threads(4)
torch.use_deterministic_algorithms(True,warn_only=True)
dtype=np.dtype([('setup','<u8'),('x','<f4',(290,)),('mask','<f4',(67,)),('action','<f4'),('value','<f4')])
assert dtype.itemsize==1444
tr=np.fromfile(a.train,dtype=dtype);dv=np.fromfile(a.dev,dtype=dtype)
assert not set(tr['setup'])&set(dv['setup'])
def tensors(rows):
    return [torch.from_numpy(np.array(rows[k],copy=True)).to(a.device) for k in ('x','mask','action','value')]
x,mask,action,value=tensors(tr);dx,dm,da,dy=tensors(dv)
class Model(nn.Module):
    def __init__(self):
        super().__init__();self.stem=nn.Linear(290,128);self.block1=nn.Linear(128,128);self.block2=nn.Linear(128,128);self.policy=nn.Linear(128,67);self.value=nn.Linear(128,1)
    def forward(self,x):
        h=torch.relu(self.stem(x));h=torch.relu(h+self.block2(torch.relu(self.block1(h))))
        return self.policy(h),self.value(h).squeeze(-1)
model=Model().to(a.device);optimizer=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.0001)
output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
best=float('inf');history=[];start=time.time()
for epoch in range(a.epochs):
    model.train();order=torch.randperm(len(x),device=a.device)
    for batch in order.split(2048):
        logits,v=model(x[batch]);logits=logits.masked_fill(mask[batch]==0,-1e9)
        policy_loss=nn.functional.cross_entropy(logits,action[batch].long())
        targets=value[batch];valid=torch.isfinite(targets)
        value_loss=nn.functional.binary_cross_entropy_with_logits(v[valid],targets[valid]) if valid.any() else v.sum()*0
        loss=policy_loss+value_loss
        optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
    model.eval();totals=np.zeros(4);nvalue=0
    with torch.no_grad():
        for i in range(0,len(dx),4096):
            sl=slice(i,i+4096);logits,v=model(dx[sl]);logits=logits.masked_fill(dm[sl]==0,-1e9);valid=torch.isfinite(dy[sl]);n=len(v)
            totals[0]+=nn.functional.cross_entropy(logits,da[sl].long(),reduction='sum').item()
            totals[1]+=(logits.argmax(-1)==da[sl]).sum().item()
            totals[2]+=nn.functional.binary_cross_entropy_with_logits(v[valid],dy[sl][valid],reduction='sum').item()
            totals[3]+=((v[valid].sigmoid()-dy[sl][valid])**2).sum().item();nvalue+=valid.sum().item()
    metrics={'epoch':epoch+1,'policy_loss':totals[0]/len(dx),'policy_accuracy':totals[1]/len(dx),'value_logloss':totals[2]/nvalue,'value_brier':totals[3]/nvalue,'seconds':time.time()-start}
    history.append(metrics);print(json.dumps(metrics),flush=True)
    score=metrics['policy_loss']+metrics['value_logloss']
    if score<best:
        best=score;torch.save(model.cpu().state_dict(),output/'model.pt');model.to(a.device)
model.load_state_dict(torch.load(output/'model.pt',map_location=a.device,weights_only=True));model.cpu().eval()
# Export row-major float32 layers, each weight matrix followed by bias.
with (output/'model.bin').open('wb') as out:
    for name in ('stem','block1','block2','policy','value'):
        layer=getattr(model,name)
        out.write(layer.weight.detach().numpy().astype('<f4').tobytes());out.write(layer.bias.detach().numpy().astype('<f4').tobytes())
with torch.no_grad():
    tx=torch.from_numpy(np.array(dv['x'][:16],copy=True));pol,val=model(tx)
(output/'parity.json').write_text(json.dumps({'x':tx.tolist(),'logits':pol.tolist(),'value_logits':val.tolist()}))
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
manifest={'seed':250000007,'device':a.device,'torch':torch.__version__,'numpy':np.__version__,'train_rows':len(tr),'dev_rows':len(dv),'train_setups':len(set(tr['setup'])),'dev_setups':len(set(dv['setup'])),'train_sha256':sha(a.train),'dev_sha256':sha(a.dev),'model_sha256':sha(output/'model.bin'),'checkpoint_sha256':sha(output/'model.pt'),'script_sha256':sha(__file__),'parameters':sum(p.numel() for p in model.parameters()),'architecture':'290 -> 128 ReLU -> residual [128 ReLU ->128] ReLU -> policy67 + value1','history':history,'selected_minimum_dev_policy_plus_value_loss':best,'determinism':'Fixed seed and deterministic algorithms requested with warnings; MPS bitwise reproducibility not guaranteed.'}
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
