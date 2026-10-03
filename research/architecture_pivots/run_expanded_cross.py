"""Complete the registered expanded large-model comparison matrix."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'expanded-cross'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'plan.json').write_text(json.dumps(dict(pairs=['history/capacity','history/entity'],games=2000,
        native_masters=[5190080000,5190090000],canonical_masters=[5180070000,5180080000],
        native_iterations=0,canonical_iterations=128,depth=16,native_workers=14,canonical_workers=32,
        scope='Direct expanded base-architecture comparisons; matched continuation remains the causal control',
        script_sha256=sha(Path(__file__))),indent=2)+'\n')
    while not (HERE/'expanded-study/registered-screens-complete.json').exists():time.sleep(30)
    # Keep the device free for any required attribution training and screens.
    while not (HERE/'expanded-attribution/complete.json').exists():time.sleep(30)
    residual=json.loads((HERE/'expanded-history/manifest.json').read_text()).get('backbone')=='capacity'
    command=[sys.executable,HERE/('service_capacity_history.py' if residual else 'service.py'),
        '--port',19541,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
    models={'capacity':HERE/'expanded-capacity/native-model.bin'}
    for kind,slot in [('entity',13),('history',14)]:
        checkpoint=HERE/f'expanded-{kind}/model.pt'
        version=json.loads(checkpoint.with_name('manifest.json').read_text()).get('history_version',1) if kind=='history' else 0
        descriptor=OUT/f'{kind}-model.bin'
        descriptor.write_bytes(b'SPREMOTE'+f'127.0.0.1:19541\n{slot}\n{sha(checkpoint)}\n{version}\n'.encode())
        models[kind]=descriptor;command+=['--model',f'{slot}:{checkpoint}']
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode in allowed,f'{name}: {result.returncode}'
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    with (OUT/'service.log').open('w') as log:
        process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        while True:
            if process.poll() is not None:raise RuntimeError('Cross-comparison service failed')
            try:
                with socket.create_connection(('127.0.0.1',19541),timeout=1):break
            except OSError:time.sleep(1)
        worker=HERE/'expanded-study/native_policy_worker.bin'
        for index,other in enumerate(('capacity','entity')):
            run(f'native-history-{other}',[sys.executable,HERE/'native_match.py','--model-a',models['history'],
                '--model-b',models[other],'--binary',worker,'--iterations-a',0,'--iterations-b',0,
                '--games',2000,'--master',5190080000+index*10000,'--workers',14,
                '--output',HERE/f'expanded-native-history-base-{other}'])
            name=f'expanded-history-base-{other}-gate';directory=HERE/name
            env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(models['history']),SPLENDOR_BEST_MODEL=str(models[other]))
            run(name,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate','--baseline','flywheel-gumbel',
                '--screen',2000,'--confirm',0,'--seed',5180070000+index*10000,'--threads',32,'--iterations',128,'--depth',16,'--output',directory],env,(0,2))
            decision=json.loads((directory/'decision.json').read_text());assert 'raw_report_sha256' in decision
            build=json.loads((directory/'build.json').read_text());frozen=directory/'splendor.bin'
            frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755);assert sha(frozen)==build['binary_sha256']
            (directory/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(models['history']),candidate_sha256=sha(models['history']),
                baseline=str(models[other]),baseline_sha256=sha(models[other]),binary_sha256=sha(frozen),
                service=json.loads((OUT/'service.log').read_text().splitlines()[0])),indent=2)+'\n')
        (OUT/'complete.json').write_text(json.dumps(dict(expanded_large_model_matrix_complete=True))+'\n')
    finally:
        process.terminate();process.wait(timeout=30)

if __name__=='__main__':main()
