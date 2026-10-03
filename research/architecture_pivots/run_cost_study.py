"""Measure final whole-game scaling and pre-calibrated fixed-cost strength."""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'cost-study'
sys.path.insert(0,str(ROOT/'scripts'))
from promote import build_release

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'plan.json').write_text(json.dumps(dict(scaling_workers=[1,4,8,14,32],scaling_games=128,
        scaling_iterations=0,scaling_master=5170000000,cost_pilot_games=32,
        candidate_budget_grid=[0,8,16,32,64,128],baseline_budget=128,cost_strength_games=2000,
        budget_rule='Nearest mean policy response cost per decision; increase baseline budget if candidate root alone costs more',
        timing='Wait for all registered expanded screens; record host activity; fixed batch32',
        script_sha256=sha(Path(__file__))),indent=2)+'\n')
    while not (HERE/'expanded-study/registered-screens-complete.json').exists():time.sleep(30)
    # Complete any required attribution training before cost measurements.
    while not (HERE/'expanded-attribution/complete.json').exists():time.sleep(30)
    while not (HERE/'expanded-cross/complete.json').exists():time.sleep(30)
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode not in allowed:raise RuntimeError(f'{name}: exit {result.returncode}')
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    original=build_release(OUT);binary=OUT/'splendor.bin';binary.write_bytes(original.read_bytes());binary.chmod(0o755)
    run('worker-build',['cargo','build','--release','--locked','--package','splendor-arena','--example','native_policy_worker'])
    worker=OUT/'native_policy_worker.bin';worker.write_bytes((ROOT/'target/release/examples/native_policy_worker').read_bytes());worker.chmod(0o755)
    # Small pilots must have enough independent shards to exercise 14 workers.
    source=(HERE/'native_match.py').read_text();old='blocks=min(50,args.games//2-offset)'
    assert old in source
    cost_match=HERE/'cost_native_match.py'
    cost_match.write_text(source.replace(old,'blocks=min(max(1,args.games//(args.workers*4)),args.games//2-offset)'))
    champion=ROOT/'research/e81/model/model.bin'
    models={kind:HERE/f'expanded-{kind}/model.bin' for kind in ('small','small-cold')}
    models['capacity']=HERE/'expanded-capacity/native-model.bin'
    entries=[('entity',13,False),('history',14,True)]
    residual_history=json.loads((HERE/'expanded-history/manifest.json').read_text()).get('backbone')=='capacity'
    command=[sys.executable,HERE/('service_capacity_history.py' if residual_history else 'service.py'),
        '--port',19538,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
    for kind,slot,history in entries:
        checkpoint=HERE/f'expanded-{kind}/model.pt';digest=sha(checkpoint)
        descriptor=OUT/f'{kind}-model.bin'
        version=json.loads((HERE/f'expanded-{kind}/manifest.json').read_text()).get('history_version',1) if history else 0
        descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:19538\n{slot}\n{digest}\n{version}\n'.encode())
        models[kind]=descriptor;command+=['--model',f'{slot}:{checkpoint}']
    with (OUT/'service.log').open('w') as log:
        process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        try:
            while True:
                if process.poll() is not None:raise RuntimeError('Cost service failed')
                try:
                    with socket.create_connection(('127.0.0.1',19538),timeout=1):break
                except OSError:time.sleep(1)
            (OUT/'host-start.json').write_text(json.dumps(dict(binary_sha256=sha(binary),worker_sha256=sha(worker),
                models={k:dict(path=str(p),sha256=sha(p)) for k,p in models.items()},
                activity=subprocess.check_output(['ps','-axo','pid,pcpu,pmem,etime,comm'],text=True)),indent=2)+'\n')
            scaling={}
            for kind,model in [('champion',champion),*models.items()]:
                reference=None;rows=[]
                for threads in (1,4,8,14,32):
                    name=f'scaling-{kind}-{threads}';output=OUT/f'{name}.json'
                    env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(model),SPLENDOR_BEST_MODEL=str(champion))
                    run(name,[binary,'compare','--agent-a','flywheel-gumbel-candidate','--agent-b','flywheel-gumbel',
                        '--games',128,'--players',2,'--seed',5170000000,'--threads',threads,'--iterations',0,
                        '--depth',16,'--width',6,'--rollout','strong','--evaluation','engine','--max-decisions',20000,'--output',output],env,(0,1))
                    d=json.loads(output.read_text());records=d['records']
                    if reference is None:reference=records
                    rows.append(dict(workers=threads,seconds=d['runtime_seconds'],games_per_second=d['games_per_second'],
                        completed=d['completed_games'],incomplete=d['incomplete_games'],
                        ordered_records_identical=records==reference,source_id=d['source_id']))
                scaling[kind]=rows
            (OUT/'scaling-summary.json').write_text(json.dumps(scaling,indent=2)+'\n')
            def native(name,model,ia,ib,master,games):
                dest=OUT/name
                run(name,[sys.executable,cost_match,'--model-a',model,'--model-b',champion,'--binary',worker,
                    '--iterations-a',ia,'--iterations-b',ib,'--games',games,'--master',master,'--workers',14,'--output',dest])
                return json.loads((dest/'summary.json').read_text()),json.loads(__import__('gzip').decompress((dest/'records.json.gz').read_bytes()))
            def costs(d,records):
                count=[0,0]
                for r in records:
                    for turn in range(len(r['actions'])):count[r['seats'][turn%2]]+=1
                return [d['policy_seconds'][i]/count[i] for i in range(2)]
            decisions={}
            for index,kind in enumerate(('capacity','entity','history')):
                pilots=[]
                for j,ia in enumerate((0,8,16,32,64,128)):
                    d,r=native(f'pilot-{kind}-{ia}-128',models[kind],ia,128,5171000000+index*100000+j*1000,32)
                    a,b=costs(d,r);pilots.append(dict(candidate=ia,baseline=128,mean_seconds=[a,b],log_ratio=abs(__import__('math').log(a/b))))
                selected=min(pilots,key=lambda p:p['log_ratio'])
                if all(p['mean_seconds'][0]>p['mean_seconds'][1] for p in pilots):
                    root=pilots[0];estimate=128*root['mean_seconds'][0]/root['mean_seconds'][1]
                    ib=min((256,512,1024,2048,4096),key=lambda b:abs(b-estimate))
                    d,r=native(f'pilot-{kind}-0-{ib}',models[kind],0,ib,5171500000+index*10000,32)
                    a,b=costs(d,r);selected=dict(candidate=0,baseline=ib,mean_seconds=[a,b],log_ratio=abs(__import__('math').log(a/b)))
                (OUT/f'{kind}-budget-selection.json').write_text(json.dumps(dict(pilots=pilots,selected=selected,
                    selection_uses_strength=False,scope='Estimated cost match at this worker/backend configuration'),indent=2)+'\n')
                d,r=native(f'matched-{kind}',models[kind],selected['candidate'],selected['baseline'],5172000000+index*10000,2000)
                a,b=costs(d,r);decisions[kind]=dict(selected=selected,actual_mean_seconds=[a,b],actual_cost_ratio=a/b,
                    within_twenty_percent=.8<=a/b<=1.2,credit=d['credit'],ci95=d['ci95'],completed=d['completed'],
                    record_set_sha256=d['record_set_sha256'])
            (OUT/'cost-strength-summary.json').write_text(json.dumps(decisions,indent=2)+'\n')
            (OUT/'complete.json').write_text(json.dumps(dict(scaling_and_estimated_cost_strength_complete=True))+'\n')
        finally:
            process.terminate();process.wait(timeout=30)

if __name__=='__main__':main()
