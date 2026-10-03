"""Paired native public-observation matches with replay and legal history."""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/strength/native'))
sys.path.insert(0,str(ROOT/'scripts'))
from upstream import Upstream,Tracker,stream,sha,PIN
from validate import RPC
from collect_evidence import record_interval

def shard(args):
    u=Upstream();rpc=[RPC([args.binary,p]) for p in (args.model_a,args.model_b)]
    try:
        with args.output.open('x') as out:
            for block in range(args.offset,args.offset+args.games//2):
                seed=stream(args.master,'setup',block);initial=u.setup(seed)
                for rotation in range(2):
                    state=initial.copy();actor=0;tracker=Tracker(u,state)
                    seats=[rotation,1-rotation]
                    for identity,r in enumerate(rpc):r.call(op='reset',seed=stream(args.master,'policy',block,identity),iterations=[args.iterations_a,args.iterations_b][identity],depth=16,search='gumbel')
                    record=dict(block=block,rotation=rotation,seed=seed,seats=seats,status='decision_limit',winners=0,ranks=[0,0],actions=[],chance_seeds=[],state_sha256=[],observation_sha256=[],policy_seconds=[0.,0.],simulations=[0,0],inferences=[0,0])
                    start=time.perf_counter()
                    for turn in range(125):
                        reward=u.rewards(state,actor)
                        if reward is not None:
                            winners=[i for i,v in enumerate(reward) if v>0]
                            record.update(status='complete',winners=sum(1<<i for i in winners),ranks=[1 if i in winners else 2 for i in range(2)],native_rewards=reward)
                            break
                        identity=seats[actor];observation=tracker.snapshot(state,actor);legal=u.legal(state,actor)
                        tick=time.perf_counter();result=rpc[identity].call(op='choose',observation=observation,legal=legal)
                        record['policy_seconds'][identity]+=time.perf_counter()-tick
                        action=result['action'];assert action in legal
                        record['simulations'][identity]+=result['simulations'];record['inferences'][identity]+=result['inferences']
                        before=[tracker.snapshot(state,actor,viewer=seats.index(i)) for i in range(2)]
                        chance=stream(args.master,'chance',block,turn);child,next_actor=u.apply(state,actor,action,chance)
                        tracker.update(state,child,actor,action)
                        for i,r in enumerate(rpc):r.call(op='observe',before=before[i],after=tracker.snapshot(child,next_actor,viewer=seats.index(i)),action=action)
                        state,actor=child,next_actor
                        record['actions'].append(action);record['chance_seeds'].append(chance)
                        record['state_sha256'].append(hashlib.sha256(state.tobytes()).hexdigest())
                        record['observation_sha256'].append(hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest())
                    record.update(scores=[int(u.game.getScore(state,i)) for i in range(2)],runtime_seconds=time.perf_counter()-start)
                    # Independent reconstruction checks each action and all chance draws.
                    replay=initial.copy();current=0
                    for action,chance,digest in zip(record['actions'],record['chance_seeds'],record['state_sha256']):
                        assert action in u.legal(replay,current)
                        replay,current=u.apply(replay,current,action,chance)
                        assert hashlib.sha256(replay.tobytes()).hexdigest()==digest
                    assert u.rewards(replay,current)==record.get('native_rewards')
                    out.write(json.dumps(record)+'\n');out.flush()
                    if record['status']!='complete':raise RuntimeError('Incomplete native game retained')
    finally:
        for r in rpc:r.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--model-a',type=Path,required=True);ap.add_argument('--model-b',type=Path,required=True)
    ap.add_argument('--binary',type=Path,default=ROOT/'target/release/examples/native_policy_worker')
    ap.add_argument('--iterations-a',type=int,default=128);ap.add_argument('--iterations-b',type=int,default=128)
    ap.add_argument('--games',type=int,default=2000);ap.add_argument('--master',type=int,required=True)
    ap.add_argument('--workers',type=int,default=8);ap.add_argument('--offset',type=int,default=0)
    ap.add_argument('--shard',action='store_true');ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();assert args.games>0 and args.games%2==0
    args.model_a=args.model_a.resolve();args.model_b=args.model_b.resolve();args.binary=args.binary.resolve();args.output=args.output.resolve()
    if args.shard:return shard(args)
    args.output.mkdir(parents=True,exist_ok=False)
    binary=args.output/'native_policy_worker.bin';binary.write_bytes(args.binary.read_bytes());binary.chmod(0o755)
    plan=dict(models=[str(args.model_a),str(args.model_b)],model_sha256=[sha(args.model_a),sha(args.model_b)],binary_sha256=sha(binary),script_sha256=sha(__file__),upstream_revision=PIN,master=args.master,games=args.games,workers=args.workers,iterations=[args.iterations_a,args.iterations_b],depth=16,world_pool=3,profile='alphazero-native-public-paired-v1',information='Public observations and preceding public events only; no privileged policy opponent',limits='Native rules include score-cap termination; these are not canonical rankings')
    (args.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    start=time.perf_counter()
    chunks=[];offset=0
    while offset<args.games//2:
        blocks=min(50,args.games//2-offset);chunks.append((offset,blocks));offset+=blocks
    def run(chunk):
        offset,blocks=chunk;dest=args.output/f'{offset:06}.jsonl'
        command=[sys.executable,__file__,'--shard','--model-a',str(args.model_a),'--model-b',str(args.model_b),'--binary',str(binary),'--master',str(args.master),'--games',str(blocks*2),'--offset',str(offset),'--iterations-a',str(args.iterations_a),'--iterations-b',str(args.iterations_b),'--output',str(dest)]
        with dest.with_suffix('.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(run,chunks))
    records=[json.loads(line) for path in sorted(args.output.glob('*.jsonl')) for line in path.read_text().splitlines()]
    assert len(records)==args.games
    elapsed=time.perf_counter()-start
    credits=[]
    for r in records:
        seat=r['seats'].index(0);credits.append(1/r['winners'].bit_count() if r['status']=='complete' and r['winners']&(1<<seat) else 0)
    raw=json.dumps(records,sort_keys=True,separators=(',',':')).encode()
    (args.output/'records.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    summary=dict(**plan,completed=sum(r['status']=='complete' for r in records),credit=sum(credits)/len(credits),ci95=record_interval(records,2,0),seconds=elapsed,games_per_second=len(records)/elapsed,record_set_sha256=hashlib.sha256(raw).hexdigest(),policy_seconds=[sum(r['policy_seconds'][i] for r in records) for i in range(2)],inferences=[sum(r['inferences'][i] for r in records) for i in range(2)],simulations=[sum(r['simulations'][i] for r in records) for i in range(2)])
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
