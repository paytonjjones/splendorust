"""Run the registered finer cost grid, then resume canonical confirmation."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'cost-refinement-v2'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def costs(summary,records):
    count=[0,0]
    for r in records:
        for turn in range(len(r['actions'])):count[r['seats'][turn%2]]+=1
    return [summary['policy_seconds'][i]/count[i] for i in range(2)]


def main():
    plan=json.loads((OUT/'PLAN.json').read_text())
    process=None
    try:
        with (OUT/'implementation.json').open('x') as output:
            output.write(json.dumps(dict(script_sha256=sha(Path(__file__)),plan_sha256=sha(OUT/'PLAN.json'),
                native_match_sha256=sha(HERE/'cost_native_match.py')),indent=2)+'\n')
        while not (HERE/'native-confirmations/complete.json').exists():time.sleep(30)
        while not (HERE/'confirmations/complete.json').exists():time.sleep(30)
        worker=HERE/'cost-study/native_policy_worker.bin'
        assert sha(worker)=='da14ca066dcbcf5e7c91fefea7c36eb0ee0d5b4b145f2e301e08d0db8bb87c3d'
        champion=ROOT/'research/e81/model/model.bin'
        assert sha(champion)=='e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8'
        models={'capacity':HERE/'expanded-capacity/native-model.bin'}
        command=[sys.executable,HERE/'service.py','--port',plan['port'],'--device','mps',
            '--batch',32,'--delay-ms',1,'--fast-entities']
        for kind,slot in [('entity',13),('history',14)]:
            checkpoint=HERE/f'expanded-{kind}/model.pt'
            version=2 if kind=='history' else 0
            descriptor=OUT/f'{kind}-model.bin'
            descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:{plan["port"]}\n{slot}\n{sha(checkpoint)}\n{version}\n'.encode())
            models[kind]=descriptor;command+=['--model',f'{slot}:{checkpoint}']
        with (OUT/'service.log').open('w') as log:
            process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        while True:
            if process.poll() is not None:raise RuntimeError('Refinement service failed')
            try:
                with socket.create_connection(('127.0.0.1',plan['port']),timeout=1):break
            except OSError:time.sleep(1)
        (OUT/'host-start.json').write_text(json.dumps(dict(worker_sha256=sha(worker),
            models={k:dict(path=str(v),sha256=sha(v)) for k,v in models.items()},
            activity=subprocess.check_output(['ps','-axo','pid,pcpu,pmem,etime,comm'],text=True)),indent=2)+'\n')
        def native(name,kind,ia,ib,master,games):
            dest=OUT/name
            command=[sys.executable,HERE/'cost_native_match.py','--model-a',models[kind],
                '--model-b',champion,'--binary',worker,'--iterations-a',ia,'--iterations-b',ib,
                '--games',games,'--master',master,'--workers',14,'--output',dest]
            with (OUT/f'{name}.log').open('w') as log:
                result=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f'{name}: exit {result.returncode}')
            d=json.loads((dest/'summary.json').read_text())
            raw=gzip.decompress((dest/'records.json.gz').read_bytes());records=json.loads(raw)
            assert len(records)==games and d['completed']==games and sha(worker)==d['binary_sha256']
            assert hashlib.sha256(raw).hexdigest()==d['record_set_sha256']
            (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
            return d,records
        results={}
        for index,kind in enumerate(('capacity','entity','history')):
            pilots=[]
            for j,(ia,ib) in enumerate(plan['grids'][kind]):
                d,r=native(f'pilot-{kind}-{ia}-{ib}',kind,ia,ib,
                    plan['calibration_master_base']+index*100000+j*1000,128)
                a,b=costs(d,r);pilots.append(dict(candidate=ia,baseline=ib,mean_seconds=[a,b],
                    log_ratio=abs(math.log(a/b))))
            selected=min(pilots,key=lambda p:p['log_ratio'])
            (OUT/f'{kind}-selection.json').write_text(json.dumps(dict(pilots=pilots,selected=selected,
                selection_uses_strength=False),indent=2)+'\n')
            d,r=native(f'matched-{kind}',kind,selected['candidate'],selected['baseline'],
                plan['strength_master_base']+index*100000,2000)
            a,b=costs(d,r);results[kind]=dict(selected=selected,actual_mean_seconds=[a,b],
                actual_cost_ratio=a/b,within_twenty_percent=.8<=a/b<=1.2,credit=d['credit'],ci95=d['ci95'],
                completed=d['completed'],master=d['master'],record_set_sha256=d['record_set_sha256'])
        (OUT/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
        (OUT/'complete.json').write_text(json.dumps(dict(required_refinement_complete=True,
            all_within_twenty_percent=all(r['within_twenty_percent'] for r in results.values())))+'\n')
    except Exception as error:
        (OUT/'failure.json').write_text(json.dumps(dict(error=repr(error)))+'\n')
        raise
    finally:
        if process:
            process.terminate();process.wait(timeout=30)


if __name__=='__main__':main()
