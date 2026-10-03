"""Check offline and Rust event/pool tensors on replayed public observations."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from history_data import ROOT,event,public_pool
from history_v2_data import event_v2
sys.path.insert(0,str(ROOT/'benchmarks/strength/native'))
from upstream import Upstream,Tracker
from validate import RPC

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=ROOT/'target/release/examples/native_policy_worker')
    ap.add_argument('--games',type=int,default=32)
    ap.add_argument('--history-version',type=int,choices=(1,2),default=1)
    args=ap.parse_args()
    archive=ROOT/'local/research/e95/dev/000000/histories.json.gz'
    records=json.loads(gzip.decompress(archive.read_bytes()))['games'][:args.games]
    rpc=RPC([str(args.binary.resolve()),str(ROOT/'research/e81/model/model.bin')])
    u=Upstream();transitions=0;blind=0;maximum=0.
    try:
        for record in records:
            state=u.setup(record['setup']);actor=0;tracker=Tracker(u,state)
            for action,chance,digest in zip(record['actions'],record['chance_seeds'],record['state_sha256']):
                before=[tracker.snapshot(state,actor,viewer=i) for i in range(2)]
                child,next_actor=u.apply(state,actor,action,chance)
                tracker.update(state,child,actor,action)
                for viewer in range(2):
                    after=tracker.snapshot(child,next_actor,viewer=viewer)
                    result=rpc.call(op='observe',before=before[viewer],after=after,action=action,include_event=True,history_version=args.history_version)
                    actual=np.array(result['public_event'],dtype='<f4')
                    expected=(event_v2 if args.history_version==2 else event)(before[viewer],after,action,actor)
                    maximum=max(maximum,float(np.max(np.abs(actual-expected))))
                    assert np.array_equal(actual,expected),(record['setup'],transitions,viewer,actual,expected)
                    assert np.array_equal(np.array(result['public_pool'],dtype='<f4'),public_pool(before[viewer]))
                    if 24<=action<27:
                        assert np.all(actual[10:15]==0) and np.all(actual[17:24]==0);blind+=1
                state,actor=child,next_actor;transitions+=1
                assert hashlib.sha256(state.tobytes()).hexdigest()==digest
            assert u.rewards(state,actor)==record['native_rewards']
    finally:rpc.close()
    result=dict(history_version=args.history_version,games=len(records),transitions=transitions,viewer_checks=transitions*2,
        blind_event_checks=blind,event_float32_bit_exact=True,pool_float32_bit_exact=True,
        maximum_abs_error=maximum,binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (Path(__file__).parent/('public-event-v2-parity.json' if args.history_version==2 else 'public-event-parity.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
