"""Audit every history prefix, auxiliary target and public unseen mask."""
import json
import argparse
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
from history_data import AUX


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--expanded',action='store_true');args=ap.parse_args()
    local=ROOT/'local/research/architecture-pivots';data=json.loads((local/('expanded-data.json' if args.expanded else 'data.json')).read_text());receipts=[]
    for split in ('train','dev'):
        for index,e in enumerate(data[split]):
            base=Path(e.get('aux_base',local/f'{split}-{index:02d}'));n=e['rows']
            rows=np.memmap(e['source'],mode='r',dtype=DTYPE)
            history_path=Path(str(base)+'.history.bin');aux_path=Path(str(base)+'.aux.bin');pool_path=Path(str(base)+'.pool.bin')
            assert history_path.stat().st_size==n*16*32*4
            assert aux_path.stat().st_size==n*8
            assert pool_path.stat().st_size==n*90*4
            h=np.memmap(history_path,mode='r',dtype='<f4',shape=(n,16,32))
            a=np.memmap(aux_path,mode='r',dtype=AUX,shape=(n,))
            pool=np.memmap(pool_path,mode='r',dtype='<f4',shape=(n,90))
            assert np.isfinite(h).all() and np.isin(h[:,:,0],[0,1]).all()
            assert np.isin(h[:,:,1],[0,1]).all() and np.isin(pool,[0,1]).all()
            valid=h[:,:,0]>0
            assert (h[:,:,31][valid]<np.repeat(rows['x'][:,6,None]/124,16,axis=1)[valid]+1e-7).all()
            assert ((a['opponent']>=-1)&(a['opponent']<81)).all()
            assert ((a['belief']>=-1)&(a['belief']<90)).all()
            count=0
            for slot in range(3):
                targets=a['belief'][:,slot];active=targets>=0;ix=np.flatnonzero(active)
                assert (pool[ix,targets[active]]==1).all();count+=len(ix)
            first=np.r_[True,rows['setup'][1:]!=rows['setup'][:-1]]
            assert (h[first]==0).all(),'history from another game'
            receipts.append(dict(split=split,index=index,rows=n,blind_targets=count,
                history_sha256=sha(history_path),aux_sha256=sha(aux_path),pool_sha256=sha(pool_path),
                all_prefixes_valid=True,all_ground_targets_in_public_pool=True))
    (ROOT/('research/architecture_pivots/expanded-history-validation.json' if args.expanded else 'research/architecture_pivots/history-validation.json')).write_text(json.dumps(receipts,indent=2)+'\n')
    print(json.dumps(dict(rows=sum(r['rows'] for r in receipts),blind_targets=sum(r['blind_targets'] for r in receipts),
        shards=len(receipts),all_past_only_and_public_pool_valid=True)))


if __name__=='__main__':main()
