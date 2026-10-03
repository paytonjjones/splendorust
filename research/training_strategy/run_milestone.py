"""Registered major-gain confirmation. No result can update champion pointers."""
import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from data import ROOT,sha
from runtime import Runtime,command_run
from strategy_summary import canonical
from resources import evaluation_resources


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--first',type=Path,required=True)
    ap.add_argument('--second',type=Path,required=True)
    ap.add_argument('--efficiency',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--port',type=int,default=19620)
    ap.add_argument('--eval-threads',type=int,choices=(32,64),default=32)
    args=ap.parse_args()
    resource=evaluation_resources(args.eval_threads)
    first,second,efficiency,out=args.first.resolve(),args.second.resolve(),args.efficiency.resolve(),args.output.resolve()
    assert all((path/'complete.json').exists() for path in (first,second,efficiency))
    sources=[('onehot',first/'onehot/runtime.pt',first/'screen-onehot/screen.json'),
        ('visits',first/'visits/runtime.pt',first/'screen-visits/screen.json'),
        ('visits-q',first/'visits-q/runtime.pt',first/'screen-visits-q/screen.json'),
        ('iterative',second/'iterative/runtime.pt',second/'iterative-v-original/screen.json'),
        ('frozen',second/'frozen/runtime.pt',second/'frozen-v-original/screen.json'),
        ('pcr',efficiency/'pcr/runtime.pt',efficiency/'pcr-v-original/screen.json')]
    endpoints=[]
    for name,checkpoint,report in sources:
        evidence=canonical(report)
        assert evidence['games']==2000
        fit=json.loads(checkpoint.with_name('manifest.json').read_text())
        assert sha(checkpoint)==fit['runtime_sha256'], 'Endpoint differs from its fit receipt'
        endpoints.append(dict(name=name,checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint),
            evidence=evidence,eligible=evidence['strict_benefit'] and evidence['credit_bounds'][0]>=.60))
    out.mkdir(parents=True,exist_ok=False)
    lock=(ROOT/'local/research/training-strategy.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock.write(str(os.getpid()));lock.flush()
    eligible=[e for e in endpoints if e['eligible']]
    selected=max(eligible,key=lambda e:e['evidence']['credit_bounds'][0]) if eligible else None
    plan=dict(schema='major-gain-confirmation-v1',pid=os.getpid(),started_at=time.time(),
        endpoints=endpoints,selected=selected,screen_master=5470000000,resource_amendment=resource,
        confirmation_master=6470000000,rule_sha256=sha(Path(__file__).with_name('MILESTONE.md')),
        controller_sha256=sha(__file__),resources_sha256=sha(Path(__file__).with_name('resources.py')))
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if selected is None:
        (out/'complete.json').write_text(json.dumps(dict(plan=plan,decision='No endpoint meets the registered major-gain condition',confirmation_run=False),indent=2)+'\n')
        print('No major-gain milestone is eligible.',flush=True)
        return
    champion=ROOT/'research/CHAMPION.json';before=champion.read_bytes()
    try:
        with Runtime([(13,ROOT/'research/entity_baseline/model.pt'),(14,Path(selected['checkpoint']))],out/'service',args.port) as runtime:
            env=dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[14]),SPLENDOR_BEST_MODEL=str(runtime.descriptors[13]))
            command_run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate',
                '--baseline','flywheel-gumbel','--players',2,'--screen',2000,'--confirm',20000,
                '--seed',5470000000,'--threads',args.eval_threads,'--iterations',128,'--depth',16,
                '--output',out/'gate'],out/'command',env,accepted=(0,2))
        path=out/'gate/confirm.json'
        confirmation=canonical(path) if path.exists() else None
        major=bool(confirmation and confirmation['games']==20000 and confirmation['strict_benefit']
                   and confirmation['credit_bounds'][0]>=.60)
        result=dict(plan=plan,confirmation=confirmation,confirmed_major_gain=major,
            strict_gate=json.loads((out/'gate/decision.json').read_text()),official_champion_unchanged=True)
        (out/'complete.json').write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        (out/'failure.json').write_text(json.dumps(dict(error=repr(error),pid=os.getpid()),indent=2)+'\n')
        raise
    finally:
        assert champion.read_bytes()==before


if __name__=='__main__':main()
