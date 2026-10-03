"""Apply the fixed milestone rule after expanded screens, controls and costs."""
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
OUT=HERE/'confirmations'
sys.path.insert(0,str(ROOT/'scripts'))
from collect_evidence import validate_report
from promote import checked_interval, completion_evidence, completion_policy, completion_rejection

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main(resume_policy=False):
    plan=dict(rule='Highest policy-valid expanded champion worst-case credit; confirm if >=48% and upper bound >=50%, or supported promotion; also supported history/parent milestone',
        champion_master_base=5220000000,parent_master=5230000000,screen=2000,confirm=20000,
        confirmation_offset=1000000000,iterations=128,depth=16,workers=32,
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
    for dependency in ('expanded-attribution/complete.json','cost-study/complete.json','native-confirmations/complete.json'):
        while not (HERE/dependency).exists():time.sleep(30)
    kinds=['small','small-cold','capacity','entity','history'];reports={}
    for kind in kinds:
        path=HERE/f'expanded-{kind}-gate/screen.json'
        d=json.loads(path.read_text());checked_interval(d,2)
        assert d['requested_games']==2000 and d['players']==2
        if completion_rejection(d) is None:reports[kind]=d
    best=max(reports,key=lambda kind:completion_evidence(reports[kind])['candidate_credit_bounds'][0]) if reports else None
    jobs=[]
    if best:
        a=reports[best]['agents'][0]
        credit=completion_evidence(reports[best])['candidate_credit_bounds'][0]
        if (credit>=.48 and a['ci95'][1]>=.5) or a['ci95'][0]>.51:
            jobs.append((f'expanded-{best}-confirmation',best,'champion',5220000000+kinds.index(best)*100000))
    parent=json.loads((HERE/'expanded-study/history-parent-selection.json').read_text())['selected']
    direct=json.loads((HERE/'expanded-history-parent-gate/screen.json').read_text());checked_interval(direct,2)
    if completion_rejection(direct) is None and direct['agents'][0]['ci95'][0]>.5:
        jobs.append(('expanded-history-parent-confirmation','history','parent',5230000000))
    (OUT/'selection.json').write_text(json.dumps(dict(best=best,jobs=jobs,
        champion_screens={k:dict(credit=d['agents'][0]['win_rate'],interval=d['agents'][0]['ci95'],
            completion=completion_evidence(d)) for k,d in reports.items()},
        parent=parent,parent_interval=direct['agents'][0]['ci95'],completion_policy=completion_policy()),indent=2)+'\n')
    if not jobs:
        (OUT/'complete.json').write_text(json.dumps(dict(required=False,reason='No supported or close selected milestone under the fixed rule'))+'\n')
        return
    models={'champion':ROOT/'research/e81/model/model.bin','small':HERE/'expanded-small/model.bin',
        'small-cold':HERE/'expanded-small-cold/model.bin','capacity':HERE/'expanded-capacity/native-model.bin'}
    entries=[(13,'expanded-entity',False),(14,'expanded-history',True)]
    if parent=='entity':entries.append((15,'expanded-entity-continuation',False))
    else:models['parent']=HERE/'expanded-capacity-continuation/native-model.bin'
    for slot,name,history in entries:
        checkpoint=HERE/name/'model.pt'
        version=json.loads(checkpoint.with_name('manifest.json').read_text()).get('history_version',1) if history else 0
        descriptor=OUT/f'{name}-model.bin'
        descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:19540\n{slot}\n{sha(checkpoint)}\n{version}\n'.encode())
        models['entity' if slot==13 else ('history' if slot==14 else 'parent')]=descriptor
    needs_service=any(models[a].read_bytes().startswith(b'SPREMOTE') or models[b].read_bytes().startswith(b'SPREMOTE') for _,a,b,_ in jobs)
    process=None
    try:
        if needs_service:
            residual=json.loads((HERE/'expanded-history/manifest.json').read_text()).get('backbone')=='capacity'
            command=[sys.executable,HERE/('service_capacity_history.py' if residual else 'service.py'),
                '--port',19540,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
            for slot,name,_ in entries:command+=['--model',f'{slot}:{HERE/name/"model.pt"}']
            with (OUT/'service.log').open('w') as log:process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            while True:
                if process.poll() is not None:raise RuntimeError('Confirmation service failed')
                try:
                    with socket.create_connection(('127.0.0.1',19540),timeout=1):break
                except OSError:time.sleep(1)
        for name,candidate,baseline,master in jobs:
            gate=HERE/name;env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(models[candidate]),SPLENDOR_BEST_MODEL=str(models[baseline]))
            command=[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate','--baseline','flywheel-gumbel',
                '--screen',2000,'--confirm',20000,'--seed',master,'--threads',32,'--iterations',128,'--depth',16,'--output',gate]
            with (OUT/f'{name}.log').open('w') as log:result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            assert result.returncode in (0,2) and (gate/'decision.json').exists()
            decision=json.loads((gate/'decision.json').read_text())
            assert 'raw_report_sha256' in decision,'Execution failure is not a completed confirmation'
            build=json.loads((gate/'build.json').read_text());frozen=gate/'splendor.bin'
            frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755);assert sha(frozen)==build['binary_sha256']
            (gate/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(models[candidate]),candidate_sha256=sha(models[candidate]),
                baseline=str(models[baseline]),baseline_sha256=sha(models[baseline]),binary_sha256=sha(frozen),
                service=json.loads((OUT/'service.log').read_text().splitlines()[0]) if process else None),indent=2)+'\n')
            (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name,stage=decision['stage'],decision=decision['decision']))+'\n')
        (OUT/'complete.json').write_text(json.dumps(dict(required=True,jobs_complete=[j[0] for j in jobs]))+'\n')
    finally:
        if process:process.terminate();process.wait(timeout=30)

if __name__=='__main__':
    assert sys.argv[1:] in ([],['--resume-completion-policy-v2.1'])
    main(bool(sys.argv[1:]))
