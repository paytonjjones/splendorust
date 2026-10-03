"""Run registered fresh-seed history screens and matched control comparisons."""
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
OUT=HERE/'initial-history-eval'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def wait_complete(path):
    while True:
        try:
            report=json.loads(path.read_text())
            if len(report['history'])==report['epochs']:return report
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(30)

def main():
    OUT.mkdir(exist_ok=True)
    binary=OUT/'native_policy_worker.bin'
    if not binary.exists():
        binary.write_bytes((ROOT/'target/release/examples/native_policy_worker').read_bytes());binary.chmod(0o755)
    history=HERE/'history/model.bin';champion=ROOT/'research/e81/model/model.bin'
    plan=dict(games=2000,iterations=128,depth=16,workers=14,
        native_master_range=[5130060000,5130120000],canonical_masters=[5100050000,5100060000],
        native_binary_sha256=sha(binary),script_sha256=sha(Path(__file__)),
        conditions=['history','entity parent','same-weight no-history inference','capacity',
            'parent continuation','history-only training','state-only auxiliary training'],
        timing='Shared host with data collection and registered training; fixed simulation budgets')
    if not (OUT/'plan.json').exists():(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (OUT/'resume-plan.json').write_text(json.dumps(dict(script_sha256=sha(Path(__file__)),
        change='Run completed training controls before waiting for canonical screens; reuse only finished raw results',
        native_binary_sha256=sha(binary),canonical_workers=32,native_workers=14),indent=2)+'\n')
    def run(name,command,env=None,allowed=(0,)):
        if (HERE/name/'summary.json').exists() or (HERE/name/'decision.json').exists():
            return
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode not in allowed:raise RuntimeError(f'{name} exit {result.returncode}')
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    def native(name,other,master):
        run(name,[sys.executable,HERE/'native_match.py','--model-a',history,'--model-b',other,
            '--binary',binary,'--iterations-a',0,'--iterations-b',0,'--games',2000,
            '--master',master,'--workers',14,'--output',HERE/name])
    for name,other,master in (
        ('native-history-policy',champion,5130060000),
        ('native-history-entity',HERE/'entity/model.bin',5130070000),
        ('native-history-no-history',HERE/'history/no-history.bin',5130080000),
        ('native-history-capacity',HERE/'capacity/native-model.bin',5130090000)):
        native(name,other,master)
    def canonical(name,baseline,master):
        env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(history),SPLENDOR_BEST_MODEL=str(baseline))
        run(name,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate',
            '--baseline','flywheel-gumbel','--screen',2000,'--confirm',0,'--seed',master,
            '--threads',32,'--iterations',128,'--depth',16,'--output',HERE/name],env,(0,2))
        directory=HERE/name
        assert (directory/'decision.json').exists(),f'{name}: no promotion decision'
        build=json.loads((directory/'build.json').read_text());frozen=directory/'splendor.bin'
        frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755)
        assert sha(frozen)==build['binary_sha256']
        ready=json.loads((HERE/'history-service.log').read_text().splitlines()[0])
        (directory/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(history),
            candidate_descriptor_sha256=sha(history),baseline=str(baseline),baseline_sha256=sha(baseline),
            binary_sha256=sha(frozen),service=ready,environment={k:env[k] for k in ('SPLENDOR_CANDIDATE_MODEL','SPLENDOR_BEST_MODEL')}),indent=2)+'\n')
    controls=[('entity-continuation',4),('history-only',5),('auxiliary-only',6)]
    for kind,slot in controls:
        wait_complete(HERE/kind/'manifest.json')
        run(f'export-{kind}',[sys.executable,HERE/'export.py',HERE/kind/'model.pt','--port',19533,'--slot',slot])
    command=[sys.executable,HERE/'service.py','--port','19533','--device','mps','--batch','32','--delay-ms','1','--fast-entities']
    for kind,slot in controls:command+=['--model',f'{slot}:{HERE/kind/"model.pt"}']
    with (OUT/'control-service.log').open('w') as log:
        service=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        try:
            while True:
                if service.poll() is not None:raise RuntimeError('Control service failed')
                try:
                    with socket.create_connection(('127.0.0.1',19533),timeout=1):break
                except OSError:time.sleep(1)
            for index,(kind,slot) in enumerate(controls):
                run(f'parity-{kind}',[ROOT/'target/release/examples/transfer_parity',HERE/kind/'model.bin',HERE/kind/'parity.json','real'])
                native(f'native-history-{kind}',HERE/kind/'model.bin',5130100000+index*10000)
            # Keep one long canonical Transformer screen active at a time.
            while not (HERE/'entity-gate/decision.json').exists():time.sleep(30)
            canonical('history-gate',champion,5100050000)
            canonical('history-parent-continuation-gate',HERE/'entity-continuation/model.bin',5100060000)
        finally:
            service.terminate();service.wait(timeout=30)
    (OUT/'complete.json').write_text(json.dumps(dict(all_registered_screens_complete=True))+'\n')

if __name__=='__main__':main()
