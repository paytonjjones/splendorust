#!/usr/bin/env python3
"""Parallel independent setup blocks; preserve shard files and exact commands."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import time
from pathlib import Path
from upstream import ROOT, sha, DEFAULT_STRENGTH_BINARY
PYTHON=ROOT/'local/strength/inference/bin/python'
DEFAULT_POLICY_BINARY=ROOT/'target/release/examples/native_policy_worker'

def validate_settings(iterations,depth,world_pool,gumbel_max_considered,chance_universes=0):
    if not 0<=iterations<=0xffffffff:raise ValueError('iterations must be in 0..=4294967295')
    if not 1<=depth<=124:raise ValueError('depth must be in 1..=124')
    if not 0<=world_pool<=64:raise ValueError('world-pool must be in 0..=64')
    if not 1<=gumbel_max_considered<=81:raise ValueError('gumbel-max-considered must be in 1..=81')
    if not 0<=chance_universes<=64:raise ValueError('chance-universes must be in 0..=64')

def run_schedule(directory,games,master,workers,iterations=128,model=None,search="puct",root_only=False,
                 depth=16,world_pool=3,gumbel_max_considered=16,policy_binary=None,strength_binary=None,
                 campaign_context=None,chance_universes=0,dynamic_fpu=False):
    if games<=0 or games%2 or workers<1 or games//2<workers:raise ValueError('invalid paired schedule')
    validate_settings(iterations,depth,world_pool,gumbel_max_considered,chance_universes)
    policy_binary=Path(policy_binary or DEFAULT_POLICY_BINARY).resolve(strict=True)
    if not policy_binary.is_file() or not os.access(policy_binary,os.X_OK):raise ValueError('policy binary must be an executable file')
    policy_binary_sha256=sha(policy_binary)
    strength_binary=Path(strength_binary or DEFAULT_STRENGTH_BINARY).resolve(strict=True)
    if not strength_binary.is_file() or not os.access(strength_binary,os.X_OK):raise ValueError('strength binary must be an executable file')
    strength_binary_sha256=sha(strength_binary)
    campaign_context=Path(campaign_context).resolve(strict=True) if campaign_context else None
    campaign_context_sha256=sha(campaign_context) if campaign_context else None
    directory.mkdir(parents=True,exist_ok=False)
    blocks=games//2;assignments=[];offset=0
    for worker in range(workers):
        count=blocks//workers+(worker<blocks%workers)
        command=[str(PYTHON),str(Path(__file__).with_name('run.py')),'--games',str(2*count),'--master',str(master),
            '--offset-block',str(offset),'--iterations',str(iterations),'--depth',str(depth),
            '--world-pool',str(world_pool),'--gumbel-max-considered',str(gumbel_max_considered),
            '--chance-universes',str(chance_universes),
            '--policy-binary',str(policy_binary),'--strength-binary',str(strength_binary),
            '--output',str(directory/f'shard-{worker:02}.jsonl')]
        if campaign_context:command+=['--campaign-context',str(campaign_context),'--campaign-games',str(games)]
        command+=['--search',search]
        if dynamic_fpu:command+=['--dynamic-fpu']
        if root_only:command+=['--root-only']
        if model:command+=['--model',str(model)]
        assignments.append(command);offset+=count
    plan=dict(games=games,master=master,workers=workers,iterations=iterations,depth=depth,world_pool=world_pool,chance_universes=chance_universes,dynamic_fpu=dynamic_fpu,
        gumbel_max_considered=gumbel_max_considered if search=='gumbel' else None,
        root_only=root_only,search=search,policy_binary_path=str(policy_binary),policy_binary_sha256=policy_binary_sha256,
        strength_binary_path=str(strength_binary),strength_binary_sha256=strength_binary_sha256,commands=assignments,
        schedule_sha256=sha(__file__),run_sha256=sha(Path(__file__).with_name('run.py')))
    if campaign_context:plan.update(campaign_context_path=str(campaign_context),campaign_context_sha256=campaign_context_sha256)
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
    shared_keys=['model_sha256','policy_binary_path','policy_binary_sha256','strength_binary_path','strength_binary_sha256','source_id','external_config','upstream_revision','upstream_checkpoint_sha256','iterations','depth','world_pool','chance_universes','dynamic_fpu','gumbel_max_considered','master','source_sha256','root_only','search','search_profile','gumbel_config']
    if campaign_context:shared_keys += ['campaign_games','campaign_freeze_path','freeze_sha256','campaign_started_at_utc',
        'campaign_context_path','campaign_context_sha256','checkpoint_path','checkpoint_sha256',
        'export_receipt_path','export_receipt_sha256','parity_binary_path','parity_binary_sha256','service_config']
    for key in shared_keys:
        assert all(m[key]==metas[0][key] for m in metas),('shard metadata differs',key)
    if campaign_context:
        assert all(m['campaign_context_path']==str(campaign_context) and
                   m['campaign_context_sha256']==campaign_context_sha256 for m in metas), 'campaign context identity differs'
    assert metas[0]['policy_binary_path']==str(policy_binary)
    assert metas[0]['policy_binary_sha256']==policy_binary_sha256
    assert metas[0]['strength_binary_path']==str(strength_binary)
    assert metas[0]['strength_binary_sha256']==strength_binary_sha256
    rows.sort(key=lambda r:r['index'])
    assert [r['index'] for r in rows]==list(range(games))
    meta=metas[0]|dict(games=games,offset_block=0,workers=workers,wall_seconds=wall,
        startup_seconds=sum(m['startup_seconds'] for m in metas),shard_metadata=metas,
        reproduction_commands=assignments,policy_binary_path=str(policy_binary),policy_binary_sha256=policy_binary_sha256,
        strength_binary_path=str(strength_binary),strength_binary_sha256=strength_binary_sha256)
    (directory/'games.jsonl').write_text('\n'.join(map(json.dumps,[meta]+rows))+'\n')
    return plan

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,required=True);p.add_argument('--master',type=int,required=True)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--iterations',type=int,default=128)
    p.add_argument('--depth',type=int,default=16);p.add_argument('--world-pool',type=int,default=3)
    p.add_argument('--gumbel-max-considered',type=int,default=16)
    p.add_argument('--chance-universes',type=int,default=0)
    p.add_argument('--dynamic-fpu',action='store_true')
    p.add_argument('--root-only',action='store_true');p.add_argument('--search',choices=['puct','gumbel'],default='puct');p.add_argument('--model',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--policy-binary',type=Path,default=DEFAULT_POLICY_BINARY)
    p.add_argument('--strength-binary',type=Path,default=DEFAULT_STRENGTH_BINARY)
    p.add_argument('--campaign-context',type=Path)
    a=p.parse_args()
    print(json.dumps(run_schedule(a.output.resolve(),a.games,a.master,a.workers,a.iterations,a.model,a.search,a.root_only,
        a.depth,a.world_pool,a.gumbel_max_considered,a.policy_binary,a.strength_binary,a.campaign_context,
        a.chance_universes,a.dynamic_fpu)),flush=True)
if __name__=='__main__':main()
