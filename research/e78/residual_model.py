"""Fixed learned base plus a zero-initialized modern correction branch."""
import struct
from pathlib import Path
import torch
from torch import nn
from flywheel_model import bootstrap,expand_trunk,export as export_base
from gated_model import Gated,export as export_delta

class Residual(nn.Module):
    def __init__(self,warmstart,width=192,blocks=3):
        super().__init__()
        payload=torch.load(warmstart,map_location='cpu',weights_only=True)
        if payload.get('architecture')=='residual':
            self.base=expand_trunk(bootstrap(),payload['base_trunk_blocks'])
            self.delta=Gated(payload['delta_width'],payload['delta_blocks'],bitplanes=True)
            self.load_state_dict(payload['state_dict'],strict=True)
        else:
            self.base=bootstrap(warmstart)
            self.delta=Gated(width,blocks,bitplanes=True)
            nn.init.zeros_(self.delta.head.weight);nn.init.zeros_(self.delta.head.bias)
        self.base.requires_grad_(False);self.base.eval()
    def train(self,mode=True):
        super().train(mode);self.base.eval();return self
    def forward(self,x):
        with torch.no_grad():
            h=self.base.trunk(self.base.first_layer(x.reshape(-1,56,7)))
            base_pi=self.base.output_layers_PI(h);base_value=self.base.output_layers_V(h)
        pi,value=self.delta.forward_raw(x)
        return base_pi+pi,(base_value+value).tanh()
    def metadata(self):
        return dict(base_trunk_blocks=len(self.base.trunk),delta_width=self.delta.width,delta_blocks=self.delta.block_count)

def export(model,path):
    path=Path(path)
    export_base(model.base,path.with_name('base.bin'));export_delta(model.delta,path.with_name('delta.bin'))
    base=path.with_name('base.bin').read_bytes();delta=path.with_name('delta.bin').read_bytes()
    path.write_bytes(b'SPRESID1'+struct.pack('<II',len(base),len(delta))+base+delta)
