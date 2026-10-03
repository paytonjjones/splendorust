"""Separate full public-action prefixes; original state/target bytes stay fixed."""
import gzip
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from history_data import ROOT,event,prefix,Upstream,Tracker
sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
HERE=Path(__file__).resolve().parent

def event_v2(before,after,action,actor):
    result=event(before,after,action,actor)
    result[15]=(action+1)/81
    if action<12:result[16]=(action+1)/12
    elif action<24:result[16]=(action-11)/12
    elif action<27:result[16]=(action-23)/3
    elif action<30:result[16]=(action-26)/3
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--initial-and-canonical',action='store_true');args=ap.parse_args()
    local=ROOT/'local/research/architecture-pivots'
    data=json.loads((local/('data.json' if args.initial_and_canonical else 'expanded-data.json')).read_text())
    if args.initial_and_canonical:
        assert len(data['train'])==26
        data['train'] += [dict(native=True,pending=True) for _ in range(100)]
        for index in range(4):
            source=local/'expansion/canonical'/f'{index:02d}.data.bin'
            data['train'].append(dict(native=False,source=str(source),context=str(source.with_suffix('.context.bin')),
                aux_base=str(local/f'expanded-canonical-{index:02d}')))
    out=HERE/'history-v2-data';out.mkdir(exist_ok=True)
    dest=local/'history-v2';dest.mkdir(exist_ok=True)
    binary=out/'flywheel_data.bin'
    if not binary.exists():shutil.copy2(ROOT/'target/release/examples/flywheel_data',binary)
    env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e81/model/model.bin')
    receipts=json.loads((out/'progress.json').read_text()) if (out/'progress.json').exists() else []
    u=None
    for split in ('train','dev'):
        for index,e in enumerate(data[split]):
            if e.get('pending'):continue
            target=dest/f'{split}-{index:03d}.history.bin'
            previous=next((r for r in receipts if (r['split'],r['index'])==(split,index)),None)
            if previous:
                assert sha(target)==previous['history_sha256'];continue
            path=Path(e['source']);rows=np.memmap(path,mode='r',dtype=DTYPE)
            base=Path(e.get('aux_base',local/f'{split}-{index:02d}'))
            if e['native']:
                if u is None:u=Upstream()
                archive=path.parent/'histories.json.gz';records=json.loads(gzip.decompress(archive.read_bytes()))['games']
                h=np.memmap(target,mode='w+',dtype='<f4',shape=(len(rows),16,32));offset=0
                for record in records:
                    state=u.setup(record['setup']);actor=0;tracker=Tracker(u,state);events=[]
                    assert np.array_equal(state,np.array(record['initial_state'],dtype=np.int8))
                    for turn,action in enumerate(record['actions']):
                        before=tracker.snapshot(state,actor)
                        assert before==record['public_observations'][turn]
                        assert rows[offset]['setup']==record['setup'] and rows[offset]['policy'].argmax()==action
                        h[offset]=prefix(events,actor)
                        child,next_actor=u.apply(state,actor,action,record['chance_seeds'][turn])
                        tracker.update(state,child,actor,action)
                        events.append(event_v2(before,tracker.snapshot(child,next_actor,viewer=actor),action,actor))
                        state,actor=child,next_actor;offset+=1
                        assert __import__('hashlib').sha256(state.tobytes()).hexdigest()==record['state_sha256'][turn]
                    assert u.rewards(state,actor)==record['native_rewards']
                assert offset==len(rows);h.flush()
                receipt=dict(replay_sha256=sha(archive))
            else:
                if path.name=='004000.bin':seed=4680004000
                elif path.name=='dev.bin':seed=4690000000
                else:seed=5120000000+int(path.name.split('.')[0])*1000
                generated=dest/f'{split}-{index:03d}.canonical.bin'
                command=[binary,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,
                    '--iterations',800,'--teacher-agent','flywheel-gumbel','--teacher-action-targets',
                    '--public-context','--public-history','--history-version',2,'--depth',16,'--threads',4,'--output',generated]
                with (out/f'{split}-{index:03d}.log').open('w') as log:
                    subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads(generated.with_suffix('.json').read_text())
                assert report['complete']==1000 and report['blocked']==report['capped']==0
                assert sha(generated)==sha(path),'state/policy/value row bytes changed'
                assert sha(generated.with_suffix('.context.bin'))==sha(Path(e['context']))
                assert sha(generated.with_suffix('.aux.bin'))==sha(Path(str(base)+'.aux.bin'))
                generated.with_suffix('.history.bin').rename(target)
                receipt=dict(binary_sha256=sha(binary),source_id=report['source'],seed=seed,
                    exact_original_row_context_aux_bytes=True)
            receipts.append(dict(split=split,index=index,rows=len(rows),history_version=2,
                source_sha256=sha(path),history_sha256=sha(target),aux_sha256=sha(Path(str(base)+'.aux.bin')),
                pool_sha256=sha(Path(str(base)+'.pool.bin')),**receipt))
            (out/'progress.json').write_text(json.dumps(receipts,indent=2)+'\n')
            print(json.dumps(receipts[-1]),flush=True)
    (out/('prime-complete.json' if args.initial_and_canonical else 'complete.json')).write_text(json.dumps(receipts,indent=2)+'\n')

if __name__=='__main__':main()
