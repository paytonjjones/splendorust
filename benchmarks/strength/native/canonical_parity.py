#!/usr/bin/env python3
"""Compare all canonical choices to the immutable pre-refactor executable."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from upstream import ROOT, sha
from validate import RPC

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,default=200);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    os.environ['SPLENDOR_CANDIDATE_MODEL']=str(ROOT/'research/e56/model/model.bin')
    binaries=[ROOT/'local/strength/baseline/target/release/examples/strength_worker',ROOT/'target/release/examples/strength_worker']
    workers=[RPC([b]) for b in binaries];digests=[];decisions=0;started=time.perf_counter()
    try:
        for game in range(a.games):
            payload=dict(op='reset',players=2,seed=4300000000+game//2,sampling_seed=5300000000+game//2,
                agent_seeds=[6300000000+game//2,7300000000+game//2],iterations=128,depth=16,
                seats=['flywheel-candidate','strong'] if game%2==0 else ['strong','flywheel-candidate'])
            for rpc in workers:rpc.call(**payload)
            trajectory=[]
            for _ in range(2000):
                snapshots=[rpc.call(op='observe') for rpc in workers]
                assert snapshots[0]==snapshots[1],('state',game,len(trajectory))
                state=snapshots[0]
                if state['outcome'] is not None or not state['legal']:break
                actions=[rpc.call(op='select')['action'] for rpc in workers]
                assert actions[0]==actions[1],('choice',game,len(trajectory),actions)
                for rpc in workers:rpc.call(op='apply',action=actions[0])
                trajectory.append(actions[0]);decisions+=1
            else:raise AssertionError('canonical parity decision limit')
            digests.append(hashlib.sha256(json.dumps(dict(actions=trajectory,final=state),sort_keys=True).encode()).hexdigest())
    finally:
        for rpc in workers:rpc.close()
    a.output.write_text(json.dumps(dict(base_revision='d9d4e4d',games=a.games,decisions=decisions,every_choice_equal=True,
        binary_sha256=[sha(b) for b in binaries],model_sha256=sha(ROOT/'research/e56/model/model.bin'),trajectory_sha256=digests,elapsed_seconds=time.perf_counter()-started),indent=2)+'\n')
    print(a.games,decisions,'canonical trajectories equal')
if __name__=='__main__':main()
