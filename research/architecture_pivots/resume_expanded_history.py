"""Resume registered history evaluation after user stopped the parent fit."""
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
OUT=HERE/'expanded-study'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def wait(path):
    while not path.exists():time.sleep(30)

def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/'registered-screens-complete.json').exists(), 'Screens already complete'
    selected=json.loads((OUT/'history-parent-selection.json').read_text())['selected']
    assert selected=='entity'
    continued_name='expanded-entity-continuation'
    stop=json.loads((HERE/continued_name/'early-stop.json').read_text())
    manifest=json.loads((HERE/continued_name/'manifest.json').read_text())
    assert sha(HERE/continued_name/'manifest.json')==stop['original_manifest_sha256']
    assert len(manifest['history'])==stop['completed_epochs']==10
    assert manifest['best_epoch']==stop['selected_epoch']==0
    assert sha(HERE/continued_name/'model.pt')==stop['selected_checkpoint_sha256']
    history=json.loads((HERE/'expanded-history/manifest.json').read_text())
    assert len(history['history'])==history['epochs']==12
    assert sha(HERE/'expanded-history/model.pt')==history['checkpoint_sha256']
    binary=OUT/'native_policy_worker.bin'
    parity=OUT/'transfer_parity.bin'
    frozen=json.loads((OUT/'runtime-binaries.json').read_text())
    assert sha(binary)==frozen['worker_sha256'] and sha(parity)==frozen['parity_sha256']
    champion=ROOT/'research/e81/model/model.bin'
    assert sha(champion)=='e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8'
    (OUT/'early-stop-resumption.json').write_text(json.dumps(dict(
        reason=stop['reason'],original_controller_sha256=sha(HERE/'run_expanded_study.py'),
        resume_controller_sha256=sha(Path(__file__)),parent_completed_epochs=10,parent_planned_epochs=12,
        parent_selected_epoch=0,parent_checkpoint_sha256=stop['selected_checkpoint_sha256'],
        history_checkpoint_sha256=history['checkpoint_sha256'],
        scope='Reuse original evaluation helper definitions and exact post-training evaluation tail; no seed, model selection, search or batching change'),indent=2)+'\n')
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode not in allowed:raise RuntimeError(f'{name}: exit {result.returncode}')
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')

    def service(entries,port,log_path,entrypoint='service.py'):
        command=[sys.executable,HERE/entrypoint,'--port',port,'--device','mps','--batch',32,'--delay-ms',1,'--fast-entities']
        for slot,checkpoint in entries:command+=['--model',f'{slot}:{checkpoint}']
        handle=log_path.open('w');process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT);handle.close()
        while True:
            if process.poll() is not None:raise RuntimeError('Expanded service failed')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=1):return process
            except OSError:time.sleep(1)

    def native(name,a,b,master,ia=0,ib=0,games=2000,workers=14):
        summary=HERE/name/'summary.json'
        if summary.exists():
            d=json.loads(summary.read_text())
            assert d['master']==master and d['games']==games and d['completed']==games
            assert d['iterations']==[ia,ib] and d['workers']==workers
            assert d['model_sha256']==[sha(a),sha(b)]
            return
        run(name,[sys.executable,HERE/'native_match.py','--model-a',a,'--model-b',b,'--binary',binary,
            '--iterations-a',ia,'--iterations-b',ib,'--games',games,'--master',master,'--workers',workers,'--output',HERE/name])

    def canonical(name,a,b,master,logs):
        directory=HERE/name
        if (directory/'decision.json').exists():
            sys.path.insert(0,str(ROOT/'scripts'))
            from collect_evidence import validate_report
            d=json.loads((directory/'screen.json').read_text());validate_report(d)
            m=json.loads((directory/'inference-manifest.json').read_text())
            decision=json.loads((directory/'decision.json').read_text())
            assert d['seed']==master and d['requested_games']==2000
            assert sha(directory/'screen.json')==decision['raw_report_sha256']
            assert m['candidate_sha256']==sha(a) and m['baseline_sha256']==sha(b)
            assert sha(directory/'splendor.bin')==m['binary_sha256']
            settings=json.loads((directory/'run.json').read_text())
            assert settings['threads']==32 and settings['iterations']==128 and settings['depth']==16
            return
        env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(a),SPLENDOR_BEST_MODEL=str(b))
        run(name,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate','--baseline','flywheel-gumbel',
            '--screen',2000,'--confirm',0,'--seed',master,'--threads',32,'--iterations',128,'--depth',16,'--output',HERE/name],env,(0,2))
        directory=HERE/name;assert (directory/'decision.json').exists()
        build=json.loads((directory/'build.json').read_text());frozen=directory/'splendor.bin'
        frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755);assert sha(frozen)==build['binary_sha256']
        ready=[json.loads(p.read_text().splitlines()[0]) for p in logs]
        (directory/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(a),candidate_sha256=sha(a),
            baseline=str(b),baseline_sha256=sha(b),binary_sha256=sha(frozen),services=ready,
            environment={k:env[k] for k in ('SPLENDOR_CANDIDATE_MODEL','SPLENDOR_BEST_MODEL')}),indent=2)+'\n')

    run('expanded-auxiliary-baselines',[sys.executable,HERE/'auxiliary_baselines.py','--expanded'])
    exporter=HERE/('export_capacity_history.py' if selected=='capacity' else 'export.py')
    for output,slot in (('expanded-history',14),(continued_name,15)):
        command=[sys.executable,exporter,HERE/output/'model.pt','--port',19535,'--slot',slot]
        if selected=='capacity' and output==continued_name:command+=['--native-capacity']
        run(f'export-{output}',command)
    run('export-expanded-no-history',[sys.executable,exporter,HERE/'expanded-history/model.pt','--port',19535,'--slot',14,'--disable-history'])
    history_log=OUT/'history-service.log'
    entries=[(14,HERE/'expanded-history/model.pt')]
    if selected=='entity':entries.append((15,HERE/continued_name/'model.pt'))
    history_service=service(entries,19535,history_log,'service_capacity_history.py' if selected=='capacity' else 'service.py')
    try:
        h=HERE/'expanded-history/model.bin';continued=HERE/continued_name/('native-model.bin' if selected=='capacity' else 'model.bin')
        run('history-probe',[sys.executable,HERE/'probe_service.py','--checkpoint',HERE/'expanded-history/model.pt',
            '--port',19535,'--slot',14,'--output',OUT/'history-service-probe.json'])
        for output,descriptor in (('expanded-history',h),(continued_name,continued)):
            run(f'parity-{output}',[parity,descriptor,HERE/output/'parity.json','real'])
        native('expanded-native-history-champion',h,champion,5190000000)
        native('expanded-native-history-parent',h,continued,5190040000)
        native('expanded-native-history-no-history',h,HERE/'expanded-history/no-history.bin',5190050000)
        canonical('expanded-history-gate',h,champion,5180000000,[history_log])
        canonical('expanded-history-parent-gate',h,continued,5180040000,[history_log])
        direct=json.loads((HERE/'expanded-history-parent-gate/screen.json').read_text())
        if direct['incomplete_games']==0 and direct['agents'][0]['ci95'][0]>.5:
            (OUT/'additional-controls-required.json').write_text(json.dumps(dict(reason='Supported history gain requires expanded history-only and state-only attribution controls'))+'\n')
        (OUT/'registered-screens-complete.json').write_text(json.dumps(dict(base_and_history_complete=True,
            conditional_attribution_pending=(OUT/'additional-controls-required.json').exists(),cost_and_confirmation_pending=True))+'\n')
    finally:
        history_service.terminate();history_service.wait(timeout=30)

if __name__=='__main__':main()
