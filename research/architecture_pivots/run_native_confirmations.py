"""Confirm supported native architecture milestones on fresh paired setups."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'native-confirmations'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'plan.json').write_text(json.dumps(dict(rule='Confirm supported entity or capacity native/E81 gain; confirm supported history/continued-parent gain',
        support='Complete 2,000-game screen, lower 95% bound above 51% for champion, above 50% for history/parent',
        games=20000,iterations=0,depth=16,workers=14,
        masters=dict(entity=5250000000,capacity=5250100000,history_parent=5250200000),
        timing='After all fits, primary screens, attribution, direct matrix and cost measurements; before canonical confirmation',
        script_sha256=sha(Path(__file__))),indent=2)+'\n')
    while not (HERE/'cost-study/complete.json').exists():time.sleep(30)
    jobs=[]
    for kind,master in [('entity',5250000000),('capacity',5250100000)]:
        d=json.loads((HERE/f'expanded-native-{kind}-champion/summary.json').read_text())
        if d['completed']==d['games']==2000 and d['ci95'][0]>.51:
            jobs.append((f'expanded-native-{kind}-confirmation',kind,'champion',master))
    d=json.loads((HERE/'expanded-native-history-parent/summary.json').read_text())
    if d['completed']==d['games']==2000 and d['ci95'][0]>.5:
        jobs.append(('expanded-native-history-parent-confirmation','history','parent',5250200000))
    (OUT/'selection.json').write_text(json.dumps(dict(jobs=jobs),indent=2)+'\n')
    if not jobs:
        (OUT/'complete.json').write_text(json.dumps(dict(required=False,reason='No supported native milestone'))+'\n')
        return
    parent=json.loads((HERE/'expanded-study/history-parent-selection.json').read_text())['selected']
    models={'champion':ROOT/'research/e81/model/model.bin','capacity':HERE/'expanded-capacity/native-model.bin'}
    entries=[(13,'expanded-entity',False),(14,'expanded-history',True)]
    if parent=='entity':entries.append((15,'expanded-entity-continuation',False))
    else:models['parent']=HERE/'expanded-capacity-continuation/native-model.bin'
    for slot,name,history in entries:
        checkpoint=HERE/name/'model.pt'
        version=json.loads(checkpoint.with_name('manifest.json').read_text()).get('history_version',1) if history else 0
        descriptor=OUT/f'{name}-model.bin'
        descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:19543\n{slot}\n{sha(checkpoint)}\n{version}\n'.encode())
        models['entity' if slot==13 else ('history' if slot==14 else 'parent')]=descriptor
    residual=json.loads((HERE/'expanded-history/manifest.json').read_text()).get('backbone')=='capacity'
    command=[sys.executable,HERE/('service_capacity_history.py' if residual else 'service.py'),
        '--port',19543,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
    for slot,name,_ in entries:command+=['--model',f'{slot}:{HERE/name/"model.pt"}']
    process=None
    try:
        with (OUT/'service.log').open('w') as log:
            process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        while True:
            if process.poll() is not None:raise RuntimeError('Native confirmation service failed')
            try:
                with socket.create_connection(('127.0.0.1',19543),timeout=1):break
            except OSError:time.sleep(1)
        worker=HERE/'expanded-study/native_policy_worker.bin'
        for name,a,b,master in jobs:
            command=[sys.executable,HERE/'native_match.py','--model-a',models[a],'--model-b',models[b],
                '--binary',worker,'--iterations-a',0,'--iterations-b',0,'--games',20000,
                '--master',master,'--workers',14,'--output',HERE/name]
            with (OUT/f'{name}.log').open('w') as log:
                result=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            assert result.returncode==0
            summary=json.loads((HERE/name/'summary.json').read_text())
            assert summary['completed']==summary['games']==20000
            (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name,credit=summary['credit'],interval=summary['ci95']))+'\n')
        (OUT/'complete.json').write_text(json.dumps(dict(required=True,jobs_complete=[j[0] for j in jobs]))+'\n')
    finally:
        if process:process.terminate();process.wait(timeout=30)

if __name__=='__main__':main()
