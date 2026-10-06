"""A second policy-improvement generation with a matched frozen-teacher control."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from data import ROOT, prepare, sha
from runtime import Runtime, command_run


def choose(first):
    def report(name):
        path = first / ('screen-'+name) / 'screen.json'
        r = json.loads(path.read_text())
        # Use record-derived intervals, not the decision file's summary label.
        sys.path.insert(0, str(ROOT/'scripts'))
        from collect_evidence import validate_report, record_interval
        validate_report(r)
        assert r['requested_games'] == 2000 and r['reproducible'] is True
        return r, record_interval(r['records'], 2, 0)
    q, q_interval = report('q-v-visits')
    soft, soft_interval = report('visits-v-onehot')
    if q['incomplete_games'] == 0 and q_interval[0] > .51:
        arm = 'visits-q'
        reason = 'Complete direct Q screen supports a benefit above the1% threshold'
    elif soft['incomplete_games'] == 0 and soft_interval[1] < .5:
        arm = 'onehot'
        reason = 'Visit targets are clearly weaker than onehot in the direct screen'
    else:
        arm = 'visits'
        reason = 'Q benefit is unconfirmed; visit targets are not clearly weaker than onehot'
    return dict(arm=arm, reason=reason, q_interval=q_interval, soft_interval=soft_interval,
                q_incomplete=q['incomplete_games'], soft_incomplete=soft['incomplete_games'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--first', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--port', type=int, default=19620)
    ap.add_argument('--device', choices=('mps','cpu'), default='mps')
    args = ap.parse_args()
    first, out = args.first.resolve(), args.output.resolve()
    assert (first/'complete.json').exists(), 'First comparison must finish before selection'
    selection = choose(first)
    parent = first/selection['arm']/'model.pt'
    current = first/selection['arm']/'runtime.pt'
    frozen = ROOT/'research/entity_baseline/model.pt'
    out.mkdir(parents=True,exist_ok=False)
    lock=(ROOT/'local/research/training-strategy.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock.write(str(os.getpid()));lock.flush()
    champion=ROOT/'research/CHAMPION.json'; champion_before=champion.read_bytes()
    collector=ROOT/'target/release/examples/rich_selfplay'
    train1=prepare(first/'train')
    epoch_rows=2*len(train1[2])
    sources=[Path(__file__),Path(__file__).with_name('strategy_train.py'),
        Path(__file__).with_name('data.py'),Path(__file__).with_name('runtime.py'),
        ROOT/'research/architecture_pivots/models.py']
    plan=dict(schema='iterative-v-frozen-teacher-v1',pid=os.getpid(),started_at=time.time(),
        selection=selection,parent_sha256=sha(parent),current_sha256=sha(current),
        frozen_sha256=sha(frozen),collector_sha256=sha(collector),
        generation1_receipt=train1[3],epoch_rows=epoch_rows,replay_fraction=[.5,.5],
        new_setups_master=5440000000,new_dev_master=5450000000,
        policy_streams=dict(iterative=9440000000,frozen=9450000000,dev=9460000000),
        source_files={str(p.relative_to(ROOT)):sha(p) for p in sources},
        unchanged_eval='canonical Gumbel128/depth16/pool3, 2,000 games, 32 workers')
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    stages=[]
    def progress(stage):
        (out/'progress.json').write_text(json.dumps(dict(stage=stage,pid=os.getpid(),
            updated_at=time.time(),completed_stages=stages),indent=2)+'\n')
        print(json.dumps(dict(stage=stage,completed=stages)),flush=True)
    try:
        with Runtime([(13,frozen),(14,current)],out/'collection-service',args.port,args.device) as runtime:
            for name,slot,games,master,policy in [('iterative-data',14,2000,5440000000,9440000000),
                ('frozen-data',13,2000,5440000000,9450000000),('dev',13,400,5450000000,9460000000)]:
                progress(name)
                command_run([collector,'--model',runtime.descriptors[slot],'--output',out/name,
                    '--games',games,'--seed',master,'--policy-seed',policy,'--threads',32,
                    '--iterations',256,'--depth',16],out/(name+'-command'))
                prepare(out/name)
                stages.append(name)
        for arm in ('iterative','frozen'):
            progress('fit-'+arm)
            command_run([sys.executable,Path(__file__).with_name('strategy_train.py'),
                '--arm',selection['arm'],'--parent',parent,'--train',first/'train',
                '--train',out/(arm+'-data'),'--dev',out/'dev','--epoch-rows',epoch_rows,
                '--output',out/arm,'--device',args.device],out/('fit-'+arm))
            stages.append('fit-'+arm)
        models=[(13,frozen),(14,current),(15,out/'iterative/runtime.pt'),(16,out/'frozen/runtime.pt')]
        comparisons=[('iterative-v-static',15,14,5461000000),('frozen-v-static',16,14,5462000000),
            ('iterative-v-frozen',15,16,5463000000),('iterative-v-original',15,13,5464000000),
            ('frozen-v-original',16,13,5465000000)]
        with Runtime(models,out/'arena-service',args.port,args.device) as runtime:
            for name,candidate,baseline,seed in comparisons:
                progress(name)
                env=dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[candidate]),
                         SPLENDOR_BEST_MODEL=str(runtime.descriptors[baseline]))
                command_run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate',
                    '--baseline','flywheel-gumbel','--players',2,'--screen',2000,'--confirm',0,
                    '--seed',seed,'--threads',32,'--iterations',128,'--depth',16,
                    '--output',out/name],out/(name+'-command'),env,accepted=(0,2))
                stages.append(name)
        assert all(sha(ROOT/k)==h for k,h in plan['source_files'].items())
        progress('complete')
        (out/'complete.json').write_text(json.dumps(dict(plan=plan,stages=stages,
            completed_at=time.time(),official_champion_unchanged=True),indent=2)+'\n')
    except BaseException as error:
        (out/'failure.json').write_text(json.dumps(dict(error=repr(error),stages=stages,pid=os.getpid()),indent=2)+'\n')
        raise
    finally:
        assert champion.read_bytes()==champion_before


if __name__=='__main__':
    main()
