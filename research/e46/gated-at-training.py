"""Gated residual student; offline PyTorch training and native binary export."""
import struct
import numpy as np
import torch
from torch import nn

MAGIC=b'SPGATED1'
class Block(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.norm=nn.RMSNorm(width,eps=1e-5)
        self.gate=nn.Linear(width,width)
        self.up=nn.Linear(width,width)
        self.down=nn.Linear(width,width)
        with torch.no_grad():self.down.weight.mul_(0.1)
    def forward(self,x):
        h=self.norm(x)
        return x+self.down(torch.nn.functional.silu(self.gate(h))*self.up(h))
class Gated(nn.Module):
    def __init__(self,width=192,blocks=3,bitplanes=False):
        super().__init__();self.width=width;self.block_count=blocks
        self.bitplanes=bitplanes
        self.stem=nn.Linear(512 if bitplanes else 392,width)
        self.blocks=nn.ModuleList([Block(width) for _ in range(blocks)])
        self.norm=nn.RMSNorm(width,eps=1e-5)
        self.head=nn.Linear(width,83)
        scale=torch.full((392,),0.1);scale[6]=1/124
        self.register_buffer('scale',scale)
        self.register_buffer('packed_indices',torch.tensor([7*row+color for row in [26,28,30] for color in range(5)]))
    def forward(self,x):
        features=x*self.scale
        if self.bitplanes:
            # Bit extraction by integer-valued remainder avoids MPS int64 kernels.
            packed=x[:,self.packed_indices].remainder(256)
            planes=torch.stack([(packed/(2**bit)).floor().remainder(2) for bit in range(8)],dim=-1).flatten(1)
            features=features.clone();features[:,self.packed_indices]=0
            features=torch.cat([features,planes],dim=1)
        h=torch.nn.functional.silu(self.stem(features))
        for block in self.blocks:h=block(h)
        y=self.head(self.norm(h))
        return y[:,:81],y[:,81:].tanh()

def export(model,path):
    expected=torch.full((392,),0.1);expected[6]=1/124
    assert torch.equal(model.scale.cpu(),expected), "native input scale mismatch"
    values=[]
    def put(x):values.append(x.detach().cpu().numpy().astype('<f4').reshape(-1))
    def dense(l):put(l.weight);put(l.bias)
    dense(model.stem)
    for b in model.blocks:
        put(b.norm.weight);dense(b.gate);dense(b.up);dense(b.down)
    put(model.norm.weight);dense(model.head)
    x=np.concatenate(values)
    assert np.isfinite(x).all()
    with open(path,'wb') as f:f.write((b'SPGATED2' if model.bitplanes else MAGIC)+struct.pack('<II',model.width,model.block_count));f.write(x.tobytes())
