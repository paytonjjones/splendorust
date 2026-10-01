"""Bootstrap architecture and exact native export. Upstream MIT license: e30/UPSTREAM-LICENSE."""
import copy
import struct
import hashlib
import sys
from pathlib import Path
import numpy as np
import torch

DTYPE = np.dtype([('setup','<u8'),('x','<f4',(392,)),('mask','<f4',(81,)),
                  ('policy','<f4',(81,)),('teacher','<f4'),('outcome','<f4')])
assert DTYPE.itemsize == 2232

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def expand_trunk(model,depth):
    assert len(model.trunk)<=depth<=8
    blocks=list(model.trunk)
    while len(blocks)<depth:
        block=copy.deepcopy(blocks[-1])
        with torch.no_grad():block.project.norm.weight.zero_();block.project.norm.bias.zero_()
        blocks.append(block)
    model.trunk=torch.nn.Sequential(*blocks)
    return model

def expand_inputs(model,rows):
    assert rows in [56,57]
    old=model.first_layer.linear
    if old.in_features==rows:
        model.input_rows=rows;return model
    assert old.in_features==56 and rows==57
    layer=copy.deepcopy(old);layer.in_features=57
    layer.weight=torch.nn.Parameter(old.weight.new_zeros((56,57)))
    with torch.no_grad():
        layer.weight.zero_();layer.weight[:,:56].copy_(old.weight)
    model.first_layer.linear=layer;model.input_rows=57
    return model

def bootstrap(warmstart=None):
    root=Path('local/strength/external/alphazero').resolve()
    sys.path.insert(0,str(root))
    source=root/'splendor/pretrained_2players.pt'
    assert sha(source)=='6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07'
    p=torch.load(source,map_location='cpu',weights_only=False)
    assert p['nn_version']==80
    m=p['full_model'].cpu();m.load_state_dict(p['state_dict'],strict=True);m.input_rows=56
    if warmstart:
        payload=torch.load(warmstart,map_location='cpu',weights_only=True)
        expand_trunk(m,payload.get('trunk_blocks') or 1)
        expand_inputs(m,payload.get('input_rows',56))
        m.load_state_dict(payload['state_dict'],strict=True)
    return m

def raw(model,x):
    h=model.trunk(model.first_layer(x.reshape(-1,getattr(model,'input_rows',56),7)))
    return model.output_layers_PI(h),model.output_layers_V(h).tanh()

def export(model,path):
    values=[]
    def put(x): values.append(x.detach().cpu().numpy().astype('<f4').reshape(-1))
    def linear(l): put(l.weight);put(l.bias)
    def norm(l):
        put(l.linear.weight)
        scale=l.norm.weight/torch.sqrt(l.norm.running_var+l.norm.eps)
        put(scale);put(l.norm.bias-l.norm.running_mean*scale)
    def block(l):
        norm(l.expand);norm(l.depthwise);linear(l.se.fc1);linear(l.se.fc2);norm(l.project)
    norm(model.first_layer)
    for trunk in model.trunk:block(trunk)
    for head in (model.output_layers_PI,model.output_layers_V):
        block(head[0]);linear(head[2]);linear(head[4])
    x=np.concatenate(values)
    assert np.isfinite(x).all()
    depth=len(model.trunk)
    rows=getattr(model,'input_rows',56)
    assert x.size*4==Path('research/e30/model.bin').stat().st_size+4*33297*(depth-1)+4*56*(rows-56)
    with open(path,'wb') as f:
        if rows==57:f.write(b'SPINFO57'+struct.pack('<II',depth,7))
        elif depth>1:f.write(b'SPMOBIL1'+struct.pack('<I',depth))
        f.write(x.tobytes())

def open_rows(paths):
    rows=[];setups=set();files=[]
    for path in paths:
        path=Path(path)
        assert path.stat().st_size>0 and path.stat().st_size%DTYPE.itemsize==0
        r=np.memmap(path,mode='r',dtype=DTYPE)
        ids=set(map(int,np.unique(r['setup'])))
        assert not ids & setups, 'duplicate setup between data shards'
        setups.update(ids);rows.append(r)
        files.append(dict(path=str(path),sha256=sha(path),rows=len(r),setups=len(ids)))
    return rows,setups,files

def check_rows(r):
    for start in range(0,len(r),8192):
        b=r[start:start+8192]
        assert np.isfinite(b['x']).all()
        assert np.isin(b['mask'],[0,1]).all() and (b['mask'].sum(-1)>0).all()
        assert np.isfinite(b['policy']).all() and (b['policy']>=0).all()
        assert (b['policy'][b['mask']==0]==0).all()
        assert np.allclose(b['policy'].sum(-1),1,atol=1e-5)
        for key in ['teacher','outcome']:
            v=b[key];assert (np.isnan(v)|((v>=0)&(v<=1))).all()
