"""Execute the registered matched-label comparison; never change champion pointers."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--port', type=int, default=19620)
    ap.add_argument('--device', choices=('mps','cpu'), default='mps')
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    lock = (ROOT / 'local/research/training-strategy.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.write(str(os.getpid()));lock.flush()
    baseline = ROOT / 'research/entity_baseline/model.pt'
    assert sha(baseline) == 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'
    champion = ROOT / 'research/CHAMPION.json'
    champion_before = champion.read_bytes()
    binary = ROOT / 'target/release/examples/rich_selfplay'
    assert binary.exists()
    sources = [ROOT/'crates/splendor-arena/examples/rich_selfplay.rs',
        ROOT/'crates/splendor-agents/src/neural_search.rs',
        ROOT/'research/architecture_pivots/models.py', Path(__file__),
        Path(__file__).with_name('strategy_train.py'), Path(__file__).with_name('data.py'),
        Path(__file__).with_name('runtime.py'), Path(__file__).with_name('PREREGISTRATION.md')]
    plan = dict(schema='matched-label-study-v1', pid=os.getpid(), started_at=time.time(),
        baseline_sha256=sha(baseline), collector_sha256=sha(binary),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_files={str(p.relative_to(ROOT)):sha(p) for p in sources},
        train=dict(games=2000,master=5410000000,policy_master=8410000000),
        dev=dict(games=400,master=5420000000,policy_master=8420000000),
        threads=32,iterations=256,depth=16,arms=['onehot','visits','visits-q'])
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    stages = []

    def progress(stage):
        (out/'progress.json').write_text(json.dumps(dict(pid=os.getpid(), stage=stage,
            updated_at=time.time(), completed_stages=stages),indent=2)+'\n')
        print(json.dumps(dict(stage=stage, completed=stages)),flush=True)

    def collect(name, runtime, games, seed, policy, threads):
        progress(name)
        result = command_run([binary,'--model',runtime.descriptors[13], '--output',out/name,
            '--games',games,'--seed',seed,'--policy-seed',policy,'--threads',threads,
            '--iterations',256,'--depth',16],out/(name+'-command'))
        prepared = prepare(out/name)
        stages.append(name)
        return result, prepared[3]

    try:
        with Runtime([(13,baseline)],out/'collection-service',args.port,args.device) as runtime:
            progress('runtime-parity')
            command_run(['cargo','run','--release','--locked','-p','splendor-arena','--example',
                         'transfer_parity','--',runtime.descriptors[13],
                         runtime.descriptors[13].with_name('parity.json'),'real'],out/'parity')
            scaling=[]
            for threads in (4,8,16,32):
                result, receipt = collect(f'scaling-{threads}',runtime,64,5401000000,8401000000,threads)
                scaling.append(dict(threads=threads,wall_seconds=result['seconds'],receipt=receipt,
                    collector=json.loads((out/f'scaling-{threads}/complete.json').read_text())))
            assert len({x['receipt']['source_sha256'] for x in scaling}) == 1, 'Scaling changed target row bytes'
            assert len({x['receipt']['history_sha256'] for x in scaling}) == 1, 'Scaling changed game records'
            (out/'scaling.json').write_text(json.dumps(scaling,indent=2)+'\n')
            collect('train',runtime,2000,5410000000,8410000000,32)
            collect('dev',runtime,400,5420000000,8420000000,32)
        for arm in plan['arms']:
            progress('fit-'+arm)
            command_run([sys.executable,Path(__file__).with_name('strategy_train.py'),
                '--arm',arm,'--train',out/'train','--dev',out/'dev','--output',out/arm,
                '--device',args.device],out/('fit-'+arm))
            stages.append('fit-'+arm)
        models=[(13,baseline)] + [(14+i,out/arm/'runtime.pt') for i,arm in enumerate(plan['arms'])]
        comparisons=[('onehot',14,13,5431000000),('visits',15,13,5432000000),
            ('visits-q',16,13,5433000000),('visits-v-onehot',15,14,5434000000),
            ('q-v-visits',16,15,5435000000)]
        with Runtime(models,out/'arena-service',args.port,args.device) as runtime:
            for name,candidate,baseline_slot,seed in comparisons:
                progress('screen-'+name)
                env=dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[candidate]),
                         SPLENDOR_BEST_MODEL=str(runtime.descriptors[baseline_slot]))
                command_run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate',
                    '--baseline','flywheel-gumbel','--players',2,'--screen',2000,'--confirm',0,
                    '--seed',seed,'--threads',32,'--iterations',128,'--depth',16,
                    '--output',out/('screen-'+name)],out/('screen-'+name+'-command'),env,accepted=(0,2))
                stages.append('screen-'+name)
        assert champion.read_bytes() == champion_before
        assert all(sha(p)==h for p,h in [(ROOT/k,v) for k,v in plan['source_files'].items()])
        progress('complete')
        (out/'complete.json').write_text(json.dumps(dict(plan=plan,stages=stages,
            completed_at=time.time(),official_champion_unchanged=True),indent=2)+'\n')
    except BaseException as error:
        (out/'failure.json').write_text(json.dumps(dict(error=repr(error),stage=stages,
            failed_at=time.time(),pid=os.getpid()),indent=2)+'\n')
        raise
    finally:
        assert champion.read_bytes() == champion_before, 'Official champion changed'


if __name__ == '__main__':
    main()
