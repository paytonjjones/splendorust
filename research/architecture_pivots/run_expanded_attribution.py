"""Run causal training controls if expanded history beats its matched parent."""
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
OUT=HERE/'expanded-attribution'
sys.path.insert(0,str(ROOT/'scripts'))
from promote import checked_interval, completion_policy, completion_rejection

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main(resume_policy=False):
    plan=dict(trigger='Policy-valid history/parent screen in either profile, lower 95% bound above 50%',
        controls=['history-only','no-history'],epochs=12,batch=512,learning_rate=.0001,
        native_masters=[5190060000,5190070000],canonical_masters=[5180050000,5180060000],
        native_workers=14,canonical_workers=32,iterations=128,depth=16,
        script_sha256=sha(Path(__file__)),completion_policy=completion_policy())
    if resume_policy:
        assert OUT.is_dir() and not (OUT/'progress.json').exists() and not (OUT/'complete.json').exists()
        registration=HERE/'promotion-policy-v2/REGISTRATION.json'
        old=json.loads((OUT/'plan.json').read_text())
        assert old['script_sha256']==json.loads(registration.read_text())['waiting_driver_sha256'][Path(__file__).name]
        amendment=HERE/'promotion-policy-v2/AMENDMENT.json'
        assert json.loads(amendment.read_text())['max_no_action_fraction']==completion_policy()['max_no_action_fraction']
        with (OUT/'completion-policy-v2.1.json').open('x') as receipt:
            receipt.write(json.dumps(dict(previous_plan_sha256=sha(OUT/'plan.json'),amendment_sha256=sha(amendment),
                resumed_plan=plan,scope='Resume waiting driver only; retain checkpoints, seeds and budgets'),indent=2)+'\n')
    else:
        OUT.mkdir(exist_ok=False)
        (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    while not (HERE/'expanded-study/registered-screens-complete.json').exists():time.sleep(30)
    direct=json.loads((HERE/'expanded-history-parent-gate/screen.json').read_text())
    interval=checked_interval(direct,2)
    native=json.loads((HERE/'expanded-native-history-parent/summary.json').read_text())
    native_supported=native['completed']==native['games'] and native['ci95'][0]>.5
    canonical_supported=completion_rejection(direct) is None and interval[0]>.5
    if not (native_supported or canonical_supported):
        (OUT/'complete.json').write_text(json.dumps(dict(required=False,reason='No supported history gain in either profile',
            parent_interval=interval,native_parent_interval=native['ci95']))+'\n')
        return
    selected=json.loads((HERE/'expanded-study/history-parent-selection.json').read_text())['selected']
    residual=selected=='capacity'
    trainer=HERE/('train_capacity_history.py' if residual else 'train_v2.py')
    exporter=HERE/('export_capacity_history.py' if residual else 'export.py')
    service_entry=HERE/('service_capacity_history.py' if residual else 'service.py')
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode not in allowed:raise RuntimeError(f'{name}: exit {result.returncode}')
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    controls=[('expanded-history-only','history-only',16),('expanded-auxiliary-only','no-history',17)]
    for name,ablation,slot in controls:
        run(f'train-{name}',[sys.executable,trainer,'--kind','history','--parent',HERE/f'expanded-{selected}/model.pt',
            '--output',HERE/name,'--history-ablation',ablation,'--data-scale','expanded','--device','mps','--fast-entities'])
        run(f'export-{name}',[sys.executable,exporter,HERE/name/'model.pt','--port',19537,'--slot',slot])
    checkpoint=HERE/'expanded-history/model.pt';descriptor=OUT/'full-history-model.bin'
    version=json.loads((checkpoint.with_name('manifest.json')).read_text())['history_version']
    digest=sha(checkpoint)
    descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:19537\n18\n{digest}\n{version}\n'.encode())
    (OUT/'full-history-export.json').write_text(json.dumps(dict(checkpoint_sha256=digest,
        descriptor_sha256=sha(descriptor),history_version=version,slot=18,port=19537),indent=2)+'\n')
    command=[sys.executable,service_entry,'--port',19537,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
    for name,slot in [('expanded-history',18),*[(n,s) for n,_,s in controls]]:
        command+=['--model',f'{slot}:{HERE/name/"model.pt"}']
    with (OUT/'service.log').open('w') as log:
        process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        try:
            while True:
                if process.poll() is not None:raise RuntimeError('Attribution service failed')
                try:
                    with socket.create_connection(('127.0.0.1',19537),timeout=1):break
                except OSError:time.sleep(1)
            worker=HERE/'expanded-study/native_policy_worker.bin'
            for index,(name,_,slot) in enumerate(controls):
                other=HERE/name/'model.bin'
                run(f'parity-{name}',[HERE/'expanded-study/transfer_parity.bin',other,HERE/name/'parity.json','real'])
                run(f'native-{name}',[sys.executable,HERE/'native_match.py','--model-a',descriptor,'--model-b',other,
                    '--binary',worker,'--iterations-a',0,'--iterations-b',0,'--games',2000,'--workers',14,
                    '--master',5190060000+index*10000,'--output',HERE/f'expanded-native-history-{name.removeprefix("expanded-")}'])
                gate=HERE/f'expanded-history-{name.removeprefix("expanded-")}-gate'
                env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(descriptor),SPLENDOR_BEST_MODEL=str(other))
                run(gate.name,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate',
                    '--baseline','flywheel-gumbel','--screen',2000,'--confirm',0,'--seed',5180050000+index*10000,
                    '--threads',32,'--iterations',128,'--depth',16,'--output',gate],env,(0,2))
                build=json.loads((gate/'build.json').read_text());frozen=gate/'splendor.bin'
                frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755)
                assert sha(frozen)==build['binary_sha256']
                (gate/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(descriptor),candidate_sha256=sha(descriptor),
                    baseline=str(other),baseline_sha256=sha(other),binary_sha256=sha(frozen),
                    service=json.loads((OUT/'service.log').read_text().splitlines()[0])),indent=2)+'\n')
            (OUT/'complete.json').write_text(json.dumps(dict(required=True,controls_complete=True,parent=selected,
                parent_interval=interval,native_parent_interval=native['ci95']))+'\n')
        finally:
            process.terminate();process.wait(timeout=30)

if __name__=='__main__':
    assert sys.argv[1:] in ([],['--resume-completion-policy-v2.1'])
    main(bool(sys.argv[1:]))
