"""Export the small native control or a checkpoint-bound research descriptor."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import torch
from models import ROOT,load,forward
sys.path.insert(0,str(ROOT/'research/e95'))
sys.path.insert(0,str(ROOT/'research'))
from public_model import export,inputs
from flywheel_model import DTYPE,sha


def main():
    ap=argparse.ArgumentParser();ap.add_argument('checkpoint',type=Path)
    ap.add_argument('--port',type=int,default=19531);ap.add_argument('--slot',type=int,default=0)
    ap.add_argument('--native-capacity',action='store_true')
    ap.add_argument('--disable-history',action='store_true')
    args=ap.parse_args();torch.set_num_threads(1)
    model,payload=load(args.checkpoint)
    dest=args.checkpoint.with_suffix('.bin')
    if args.disable_history:
        assert payload['kind']=='history'
        dest=args.checkpoint.with_name('no-history.bin')
    if args.native_capacity:
        assert payload['kind']=='capacity'
        dest=args.checkpoint.with_name('native-model.bin')
        import struct
        parameters=[]
        def append(module):
            parameters.extend((module.weight.detach().numpy().astype('<f4').tobytes(),module.bias.detach().numpy().astype('<f4').tobytes()))
        append(model.stem)
        for block in model.blocks:
            append(block.norm);append(block.up);append(block.down)
        append(model.norm);append(model.policy);append(model.value)
        dest.write_bytes(b'SPLARGE1'+struct.pack('<II',512,8)+b''.join(parameters))
    elif payload['kind'] in ('small','small-cold'):
        export(model,dest)
    else:
        digest=sha(args.checkpoint)
        dest.write_bytes(b'SPREMOTE'+f'127.0.0.1:{args.port}\n{args.slot}\n{digest}\n{int(payload["kind"]=="history" and not args.disable_history)}\n'.encode())
    rows=np.memmap(ROOT/'local/research/e95/dev/000000/data.bin',mode='r',dtype=DTYPE)
    context=np.fromfile(ROOT/'local/research/e95/dev/000000/data.context.bin',dtype='<f4').reshape(-1,7)
    ix=np.linspace(0,len(rows)-1,32,dtype=int)
    x=rows['x'][ix].copy();c=context[ix]
    with torch.inference_mode():
        logits,values=forward(model,payload['kind'],torch.from_numpy(inputs(x,c,True)))[:2]
    dest.with_name('parity.json').write_text(json.dumps(dict(x=x.tolist(),context=c.tolist(),
        native_profiles=[True]*len(x),logits=logits.tolist(),values=values.tolist()))+'\n')
    dest.with_name('native-export.json' if args.native_capacity else 'export.json').write_text(json.dumps(dict(checkpoint_sha256=sha(args.checkpoint),
        descriptor_sha256=sha(dest),kind=payload['kind'],slot=args.slot,port=args.port,
        runtime='native' if args.native_capacity or payload['kind'].startswith('small') else 'tensor-only-service'),indent=2)+'\n')


if __name__=='__main__':main()
