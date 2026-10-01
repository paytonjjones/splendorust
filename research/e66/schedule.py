#!/usr/bin/env python3
"""Parallel independent setup blocks; preserve shard files and exact commands."""
import argparse
import concurrent.futures
import json
import subprocess
import time
from pathlib import Path
from upstream import ROOT, sha
PYTHON=ROOT/'local/strength/inference/bin/python'

def run_schedule(directory,games,master,workers,iterations=128,model=None):
    if games<=0 or games%2 or workers<1 or games//2<workers:raise ValueError('invalid paired schedule')
    directory.mkdir(parents=True,exist_ok=False)
    blocks=games//2;assignments=[];offset=0
    for worker in range(workers):
        count=blocks//workers+(worker<blocks%workers)
        command=[str(PYTHON),str(Path(__file__).with_name('run.py')),'--games',str(2*count),'--master',str(master),
            '--offset-block',str(offset),'--iterations',str(iterations),'--output',str(directory/f'shard-{worker:02}.jsonl')]
        if model:command+=['--model',str(model)]
        assignments.append(command);offset+=count
    plan=dict(games=games,master=master,workers=workers,iterations=iterations,commands=assignments,
        schedule_sha256=sha(__file__),run_sha256=sha(Path(__file__).with_name('run.py')))
    (directory/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    def execute(item):
        worker,command=item
        with (directory/f'shard-{worker:02}.log').open('w') as log:
            started=time.perf_counter();result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
            return dict(worker=worker,exit=result.returncode,wall_seconds=time.perf_counter()-started)
    started=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        executions=list(pool.map(execute,enumerate(assignments)))
    wall=time.perf_counter()-started
    plan.update(executions=executions,wall_seconds=wall)
    (directory/'execution.json').write_text(json.dumps(plan,indent=2)+'\n')
    if any(e['exit']!=0 for e in executions):raise RuntimeError('failed shard retained; schedule is incomplete')
    rows=[];metas=[]
    for worker in range(workers):
        meta,*part=map(json.loads,(directory/f'shard-{worker:02}.jsonl').read_text().splitlines())
        assert len(part)==meta['games']
        metas.append(meta);rows+=part
    for key in ['model_sha256','policy_binary_sha256','source_id','external_config','upstream_revision','upstream_checkpoint_sha256','iterations','depth','master','source_sha256']:
        assert all(m[key]==metas[0][key] for m in metas),('shard metadata differs',key)
    rows.sort(key=lambda r:r['index'])
    assert [r['index'] for r in rows]==list(range(games))
    meta=metas[0]|dict(games=games,offset_block=0,workers=workers,wall_seconds=wall,
        startup_seconds=sum(m['startup_seconds'] for m in metas),shard_metadata=metas,
        reproduction_commands=assignments)
    (directory/'games.jsonl').write_text('\n'.join(map(json.dumps,[meta]+rows))+'\n')
    return plan

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,required=True);p.add_argument('--master',type=int,required=True)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--iterations',type=int,default=128)
    p.add_argument('--model',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run_schedule(a.output.resolve(),a.games,a.master,a.workers,a.iterations,a.model)),flush=True)
if __name__=='__main__':main()
