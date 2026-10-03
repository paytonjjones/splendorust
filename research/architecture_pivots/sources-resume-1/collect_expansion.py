"""Fresh expert games for a matched data-scaling follow-up."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--games',type=int,default=20000)
    ap.add_argument('--workers',type=int,default=8);ap.add_argument('--master',type=int,default=5110000000)
    args=ap.parse_args();out=ROOT/'research/architecture_pivots/expansion'
    out.mkdir(parents=True,exist_ok=False)
    local=ROOT/'local/research/architecture-pivots/expansion/train';local.mkdir(parents=True,exist_ok=False)
    collector=ROOT/'research/e95/collect.py';worker=ROOT/'local/research/e92/frozen/native_policy_worker'
    plan=dict(games=args.games,workers=args.workers,master=args.master,shard_games=200,
        split='train only; existing disjoint development remains fixed',
        reason='Initial capacity model has worsening development fit as training loss falls; expand games before an architecture conclusion',
        hashes={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),collector,worker,
               ROOT/'research/e81/model/model.bin',ROOT/'local/strength/external/alphazero/splendor/pretrained_2players.pt']})
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');start=time.monotonic()
    def collect(offset):
        dest=local/f'{offset:06}';log=out/f'{offset:06}.log'
        with log.open('w') as stream:
            proc=subprocess.run([sys.executable,str(collector),'--master',str(args.master),
                '--offset',str(offset),'--games',str(min(200,args.games-offset)),'--output',str(dest)],
                cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        if proc.returncode:raise RuntimeError(f'{log}: exit {proc.returncode}')
        return json.loads((dest/'checks.json').read_text())
    receipts=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(collect,i) for i in range(0,args.games,200)]
        for future in concurrent.futures.as_completed(futures):
            receipts.append(future.result())
            result=dict(completed_games=sum(r['games'] for r in receipts),
                rows=sum(r['rows'] for r in receipts),seconds=time.monotonic()-start,receipts=receipts)
            (out/'progress.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({k:v for k,v in result.items() if k!='receipts'}),flush=True)
    assert sum(r['games'] for r in receipts)==args.games
    assert all(sha(ROOT/p)==h for p,h in plan['hashes'].items())
    (out/'complete.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
