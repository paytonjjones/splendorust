"""Frozen E81 leaf network with a learned519-feature public root correction."""
import struct,sys
from pathlib import Path
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import bootstrap,export as export_base
from gated_model import Gated,export as export_delta
class PublicDelta(Gated):
 def __init__(self,width=192,blocks=3):
  super().__init__(width,blocks);self.stem=nn.Linear(519,width)
  nn.init.zeros_(self.head.weight);nn.init.zeros_(self.head.bias)
 def forward_raw(self,features):
  assert features.shape[1]==519
  h=torch.nn.functional.silu(self.stem(features))
  for block in self.blocks:h=block(h)
  y=self.head(self.norm(h));return y[:,:81],y[:,81:]
class BeliefResidual(nn.Module):
 def __init__(self,warmstart,width=192,blocks=3):
  super().__init__();self.base=bootstrap(warmstart);self.delta=PublicDelta(width,blocks)
  self.base.requires_grad_(False);self.base.eval()
 def train(self,mode=True):
  super().train(mode);self.base.eval();return self
 def forward(self,x):
  assert x.shape[1]==1303
  mean=x[:,392:784];features=x[:,784:]
  with torch.no_grad():
   h=self.base.trunk(self.base.first_layer(mean.reshape(-1,56,7)))
   pi=self.base.output_layers_PI(h);value=self.base.output_layers_V(h)
  dp,dv=self.delta.forward_raw(features);return pi+dp,(value+dv).tanh()
 def metadata(self):
  return dict(base_trunk_blocks=len(self.base.trunk),delta_width=self.delta.width,delta_blocks=self.delta.block_count,public_features=519)
def export(model,path):
 path=Path(path);export_base(model.base,path.with_name('base.bin'));export_delta(model.delta,path.with_name('delta.bin'))
 base=path.with_name('base.bin').read_bytes();delta=path.with_name('delta.bin').read_bytes();delta=b'SPGATED3'+delta[8:]
 path.with_name('delta.bin').write_bytes(delta)
 path.write_bytes(b'SPBELF01'+struct.pack('<II',len(base),len(delta))+base+delta)
