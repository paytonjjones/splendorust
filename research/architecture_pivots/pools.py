"""Recover the public unseen set, including zero-deck cases, from sampled rows."""
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'research/e86'))
from flywheel_model import DTYPE,sha
from public_features import TIER,GROUP,SLOT,COST,BONUS,POINTS


def unseen(x,context):
    pool=((x[:,(26+2*TIER)*7+GROUP].astype(np.int32)&255)&(128>>SLOT))!=0
    for slot in range(3):
        active=context[:,slot]==1
        if not active.any():continue
        r=50+2*slot;t=np.rint(context[active,slot+3]*3).astype(int)-1
        match=(x[active,r*7:r*7+5,None]==COST.T).all(1)&(x[active,(r+1)*7:(r+1)*7+5,None]==BONUS.T).all(1)&(x[active,(r+1)*7+6,None]==POINTS)&(t[:,None]==TIER)
        assert (match.sum(1)==1).all()
        ids=match.argmax(1);rows=np.flatnonzero(active)
        assert not pool[rows,ids].any();pool[rows,ids]=True
    return pool.astype('<f4')


def main():
    local=ROOT/'local/research/architecture-pivots'
    data=json.loads((local/'data.json').read_text());receipts=[]
    for split in ('train','dev'):
        for index,e in enumerate(data[split]):
            rows=np.memmap(e['source'],mode='r',dtype=DTYPE)
            ctx=np.fromfile(e['context'],dtype='<f4').reshape(-1,7)
            dest=local/f'{split}-{index:02d}.pool.bin'
            pool=np.memmap(dest,mode='w+',dtype='<f4',shape=(len(rows),90))
            for i in range(0,len(rows),4096):pool[i:i+4096]=unseen(rows['x'][i:i+4096],ctx[i:i+4096])
            pool.flush()
            receipts.append(dict(split=split,index=index,rows=len(rows),pool_sha256=sha(dest),
                source_sha256=e['source_sha256'],context_sha256=e['context_sha256'],
                method='Sampled unknown reservations union sampled deck membership; no privileged label used'))
    (ROOT/'research/architecture_pivots/pool-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')


if __name__=='__main__':main()
