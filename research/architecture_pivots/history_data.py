"""Replay frozen histories. Only public past events enter model tensors."""
import argparse
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'))
sys.path.insert(0,str(ROOT/'research/e85'))
sys.path.insert(0,str(ROOT/'benchmarks/strength/native'))
from flywheel_model import DTYPE,sha
from belief import CARDS,COLORS
from upstream import Upstream,Tracker

AUX=np.dtype([('opponent','<i2'),('belief','<i2',(3,))])


def event(before,after,action,actor):
    """Actor is absolute here; convert to root-relative only at model input."""
    result=np.zeros(32,dtype='<f4');result[0]=1;result[1]=actor
    card=255;tier=0
    if action<12:
        kind=3;card=before['market'][action]
    elif action<24:
        kind=1;card=before['market'][action-12]
    elif action<27:
        kind=2;tier=(action-23)/3
    elif action<30:
        kind=4
        # Purchase reveals the card; a prior blind reservation never does.
        bought=set(after['players'][actor]['owned'])-set(before['players'][actor]['owned'])
        assert len(bought)==1;card=bought.pop()
    else:
        kind=0
    result[2+kind]=1
    if card !=255:
        c=CARDS[card]
        result[10:15]=[int(c[k])/10 for k in COLORS]
        result[17+COLORS.index(c['bonus'])]=.1
        result[23]=int(c['points'])/10
        tier=int(c['tier'])/3
    result[24:30]=(np.array(after['players'][actor]['tokens'])-
                          np.array(before['players'][actor]['tokens']))/10
    result[30]=tier;result[31]=before['turns']/124
    return result


def prefix(events,viewer):
    result=np.zeros((16,32),dtype='<f4')
    past=events[-16:]
    if past:
        result[-len(past):]=past
        result[-len(past):,1]=(result[-len(past):,1]!=viewer)
    return result


def public_pool(observation):
    result=np.ones(90,dtype='<f4')
    known={id for id in observation['market'] if id!=255}
    for seat,p in enumerate(observation['players']):
        known.update(p['owned'])
        for r in p['reserved'][:p['reserved_count']]:
            if seat==observation['viewer'] or r['public']:
                if r['card']!=255:known.add(r['card'])
            else:assert r['card']==255
    result[list(known)]=0
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--split',choices=('train','dev'),required=True)
    ap.add_argument('--directory',type=Path)
    ap.add_argument('--prefix')
    args=ap.parse_args();start=time.monotonic();u=Upstream();receipts=[]
    local=ROOT/'local/research/architecture-pivots';local.mkdir(exist_ok=True,parents=True)
    directory=args.directory or ROOT/f'local/research/e95/{args.split}'
    prefix_name=args.prefix or args.split
    for index,path in enumerate(sorted(directory.glob('*/data.bin'))):
        history_path=path.parent/'histories.json.gz'
        records=json.loads(gzip.decompress(history_path.read_bytes()))['games']
        rows=np.memmap(path,mode='r',dtype=DTYPE)
        history_dest=local/f'{prefix_name}-{index:02d}.history.bin'
        aux_dest=local/f'{prefix_name}-{index:02d}.aux.bin'
        pool_dest=local/f'{prefix_name}-{index:02d}.pool.bin'
        histories=np.memmap(history_dest,mode='w+',dtype='<f4',shape=(len(rows),16,32))
        aux=np.memmap(aux_dest,mode='w+',dtype=AUX,shape=(len(rows),))
        pools=np.memmap(pool_dest,mode='w+',dtype='<f4',shape=(len(rows),90))
        offset=0;blind=0
        for record in records:
            state=u.setup(record['setup']);assert np.array_equal(state,np.array(record['initial_state'],dtype=np.int8))
            tracker=Tracker(u,state);current=0;events=[]
            for turn,action in enumerate(record['actions']):
                observation=tracker.snapshot(state,current)
                assert observation==record['public_observations'][turn]
                assert rows[offset]['setup']==record['setup']
                assert rows[offset]['policy'].argmax()==action
                histories[offset]=prefix(events,current)
                pools[offset]=public_pool(observation)
                aux[offset]['opponent']=-1;aux[offset]['belief']=-1
                for future in range(turn+1,len(record['actions'])):
                    if record['actors'][future]!=current:
                        aux[offset]['opponent']=record['actions'][future];break
                # This full snapshot is label-only. Do not pass it to event().
                privileged=tracker.snapshot(state,current,full=True)
                opponent=1-current
                for slot,r in enumerate(observation['players'][opponent]['reserved']):
                    if slot<observation['players'][opponent]['reserved_count'] and not r['public']:
                        assert r['card']==255
                        target=privileged['players'][opponent]['reserved'][slot]['card']
                        assert 0<=target<90
                        aux[offset]['belief'][slot]=target;blind+=1
                        assert pools[offset,target]==1
                child,new_current=u.apply(state,current,action,record['chance_seeds'][turn])
                tracker.update(state,child,current,action)
                # Keep the same viewer for both public snapshots.
                after=tracker.snapshot(child,new_current,viewer=current)
                events.append(event(observation,after,action,current))
                state,current=child,new_current
                assert hashlib.sha256(state.tobytes()).hexdigest()==record['state_sha256'][turn]
                offset+=1
            assert u.rewards(state,current)==record['native_rewards']
        assert offset==len(rows);histories.flush();aux.flush();pools.flush()
        receipt=dict(split=args.split,index=index,rows=len(rows),blind_targets=blind,
            source_sha256=sha(path),replay_sha256=sha(history_path),history_sha256=sha(history_dest),
            aux_sha256=sha(aux_dest),pool_sha256=sha(pool_dest),seconds=time.monotonic()-start)
        receipts.append(receipt);print(json.dumps(receipt),flush=True)
    (ROOT/f'research/architecture_pivots/{prefix_name}-history-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')


if __name__=='__main__':
    main()
