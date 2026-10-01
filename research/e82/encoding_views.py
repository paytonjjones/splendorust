"""Alternate observation-derived inputs with original labels and row order."""
from pathlib import Path
import numpy as np
from flywheel_model import sha
DTYPE=np.dtype([('row','<u8'),('x','<f4',(7,392))])
assert DTYPE.itemsize==10984

def open_views(paths,rows):
    groups=[];files=[]
    static=np.ones(392,dtype=bool)
    static[25*7:31*7]=False;static[50*7:56*7]=False
    for name,base in zip(paths,rows):
        path=Path(name).with_suffix('.views.bin')
        size=path.stat().st_size
        assert size%DTYPE.itemsize==0
        data=np.memmap(path,mode='r',dtype=DTYPE) if size else np.empty(0,dtype=DTYPE)
        assert not len(data) or ((data['row']<len(base)).all() and (np.diff(data['row'].astype(np.int64))>0).all())
        for start in range(0,len(data),1024):
            b=data[start:start+1024];assert np.isfinite(b['x']).all()
            original=base['x'][b['row'].astype(np.int64)]
            assert np.array_equal(b['x'][:,:,static],np.broadcast_to(original[:,None,static],b['x'][:,:,static].shape)),'public feature mismatch'
        groups.append(data);files.append(dict(path=str(path),sha256=sha(path),groups=len(data),base_sha256=sha(name)))
    return groups,files

def sample_views(original,indices,groups,rng):
    result=np.array(original,copy=True)
    if not len(groups):return result
    locations=np.searchsorted(groups['row'],indices)
    present=locations<len(groups)
    present[present]&=groups['row'][locations[present]]==indices[present]
    views=rng.integers(0,8,size=len(indices))
    chosen=present&(views>0)
    result[chosen]=groups['x'][locations[chosen],views[chosen]-1]
    return result
