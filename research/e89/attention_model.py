"""Small structured public-root transformer, frozen fast bootstrap leaves."""
import sys,struct
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import bootstrap,export as export_base
class Block(nn.Module):
 def __init__(self):
  super().__init__();self.norm1=nn.RMSNorm(64,eps=1e-5);self.qkv=nn.Linear(64,192);self.out=nn.Linear(64,64)
  self.norm2=nn.RMSNorm(64,eps=1e-5);self.gate=nn.Linear(64,128);self.up=nn.Linear(64,128);self.down=nn.Linear(128,64)
 def forward(self,x):
  b,n,w=x.shape;q,k,v=self.qkv(self.norm1(x)).reshape(b,n,3,4,16).permute(2,0,3,1,4).unbind(0)
  a=(q@k.transpose(-1,-2)/4).softmax(-1)@v
  x=x+self.out(a.transpose(1,2).reshape(b,n,w));h=self.norm2(x)
  return x+self.down(torch.nn.functional.silu(self.gate(h))*self.up(h))
class Attention(nn.Module):
 def __init__(self):
  super().__init__();self.row=nn.Linear(7,64);self.global_input=nn.Linear(127,64);self.position=nn.Parameter(torch.randn(57,64)*.01)
  self.blocks=nn.ModuleList([Block(),Block()]);self.norm=nn.RMSNorm(64,eps=1e-5);self.head=nn.Linear(64,83)
  nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)
  self.width=64;self.block_count=2
 def forward_raw(self,features):
  rows=self.row(features[:,:392].reshape(-1,56,7));global_row=self.global_input(features[:,392:]).unsqueeze(1)
  x=torch.cat([global_row,rows],dim=1)+self.position
  for block in self.blocks:x=block(x)
  y=self.head(self.norm(x[:,0]));return y[:,:81],y[:,81:]
class AttentionResidual(nn.Module):
 def __init__(self,warmstart,width=64,blocks=2):
  super().__init__();assert width==64 and blocks==2
  payload=torch.load(warmstart,map_location='cpu',weights_only=True)
  continued=payload.get('architecture')=='attention-residual'
  self.base=bootstrap(ROOT/'research/e81/model/model.pt' if continued else warmstart);self.delta=Attention()
  if continued:
   assert payload['attention_heads']==4 and payload['delta_width']==64 and payload['delta_blocks']==2
   self.load_state_dict(payload['state_dict'],strict=True)
  self.base.requires_grad_(False);self.base.eval()
 def train(self,mode=True):
  super().train(mode);self.base.eval();return self
 def forward(self,x):
  assert x.shape[1]==1303
  with torch.no_grad():
   h=self.base.trunk(self.base.first_layer(x[:,392:784].reshape(-1,56,7)))
   pi=self.base.output_layers_PI(h);value=self.base.output_layers_V(h)
  dp,dv=self.delta.forward_raw(x[:,784:]);return pi+dp,(value+dv).tanh()
 def metadata(self):return dict(base_trunk_blocks=len(self.base.trunk),delta_width=64,delta_blocks=2,public_features=519,attention_heads=4)
def export(model,path):
 path=Path(path);export_base(model.base,path.with_name('base.bin'));base=path.with_name('base.bin').read_bytes();values=[]
 def put(x):values.append(x.detach().cpu().numpy().astype('<f4').reshape(-1))
 def dense(x):put(x.weight);put(x.bias)
 d=model.delta;dense(d.row);dense(d.global_input);put(d.position)
 for block in d.blocks:
  put(block.norm1.weight);dense(block.qkv);dense(block.out);put(block.norm2.weight);dense(block.gate);dense(block.up);dense(block.down)
 put(d.norm.weight);dense(d.head);payload=np.concatenate(values);assert np.isfinite(payload).all()
 path.write_bytes(b'SPATTN01'+struct.pack('<I',len(base))+base+payload.tobytes())
