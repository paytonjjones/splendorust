"""Evaluate matched expanded models, then run a matched history follow-up."""
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
    OUT.mkdir(exist_ok=False)
    plan=dict(base_kinds=['small','small-cold','capacity','entity'],games=2000,canonical_workers=32,native_workers=14,
        canonical_champion_master=5180000000,native_champion_master=5190000000,
        selection='Use direct canonical entity/capacity strength; if inconclusive, lower matched dev selection score',
        history='12 extra epochs from selected expanded parent; entity history or residual plus four history-attention layers; equal-budget parent continuation; same-weight no-history inference',
        conditional_controls='If history shows a supported direct gain, train history-only and state-only auxiliary controls',
        budgets='Canonical Gumbel128/depth16. Native policy-only first. Fixed seeds and public inference only.',
        script_sha256=sha(Path(__file__)))
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    wait(HERE/'expanded-run/complete.json')
    wait(HERE/'initial-history-eval/complete.json')
    wait(HERE/'expanded-early/complete.json')
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode not in allowed:raise RuntimeError(f'{name}: exit {result.returncode}')
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    # Build and freeze the current worker after all queued test builds.
    run('worker-build',['cargo','build','--release','--locked','--package','splendor-arena','--example','native_policy_worker'])
    binary=OUT/'native_policy_worker.bin';binary.write_bytes((ROOT/'target/release/examples/native_policy_worker').read_bytes());binary.chmod(0o755)
    run('parity-build',['cargo','build','--release','--locked','--package','splendor-arena','--example','transfer_parity'])
    parity=OUT/'transfer_parity.bin';parity.write_bytes((ROOT/'target/release/examples/transfer_parity').read_bytes());parity.chmod(0o755)
    (OUT/'runtime-binaries.json').write_text(json.dumps(dict(worker_sha256=sha(binary),parity_sha256=sha(parity)),indent=2)+'\n')
    champion=ROOT/'research/e81/model/model.bin';models={}
    for index,kind in enumerate(plan['base_kinds']):
        checkpoint=HERE/f'expanded-{kind}/model.pt'
        command=[sys.executable,HERE/'export.py',checkpoint,'--port',19534,'--slot',10+index]
        if kind=='capacity':command+=['--native-capacity']
        run(f'export-{kind}',command)
        models[kind]=checkpoint.with_name('native-model.bin' if kind=='capacity' else 'model.bin')
    service_log=OUT/'base-service.log'
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
    base_service=service([(13,HERE/'expanded-entity/model.pt')],19534,service_log)
    try:
        run('entity-probe',[sys.executable,HERE/'probe_service.py','--checkpoint',HERE/'expanded-entity/model.pt',
            '--port',19534,'--slot',13,'--output',OUT/'entity-service-probe.json'])
        for kind in plan['base_kinds']:
            run(f'parity-base-{kind}',[parity,models[kind],HERE/f'expanded-{kind}/parity.json','real'])
        for kind in plan['base_kinds']:
            native(f'expanded-native-{kind}-champion',models[kind],champion,5190000000)
        native('expanded-native-entity-capacity',models['entity'],models['capacity'],5190020000)
        native('expanded-native-entity-cold-small',models['entity'],models['small-cold'],5190030000)
        for kind in plan['base_kinds']:
            canonical(f'expanded-{kind}-gate',models[kind],champion,5180000000,[service_log])
        canonical('expanded-entity-capacity-gate',models['entity'],models['capacity'],5180020000,[service_log])
        canonical('expanded-entity-cold-small-gate',models['entity'],models['small-cold'],5180030000,[service_log])
        comparison=json.loads((HERE/'expanded-entity-capacity-gate/screen.json').read_text())
        interval=comparison['agents'][0]['ci95']
        scores={kind:json.loads((HERE/f'expanded-{kind}/manifest.json').read_text()) for kind in ('capacity','entity')}
        def score(kind):
            m=scores[kind]
            return (m['initial'] if m['best_epoch']==0 else next(r for r in m['history'] if r['epoch']==m['best_epoch']))['selection_score']
        selected='entity' if interval[0]>.5 else ('capacity' if interval[1]<.5 else min(scores,key=score))
        (OUT/'history-parent-selection.json').write_text(json.dumps(dict(selected=selected,
            canonical_direct_interval=interval,dev_scores={k:score(k) for k in scores},
            rule='Canonical direct strength if conclusive; otherwise matched held-out fit'),indent=2)+'\n')
        parent=HERE/f'expanded-{selected}/model.pt'
        continued_name=f'expanded-{selected}-continuation'
        run('history-v2-data',[sys.executable,HERE/'history_v2_data.py'])
        run('history-v2-validation',[sys.executable,HERE/'validate_history_v2.py','--expanded'])
        for kind,output in (('history','expanded-history'),(selected,continued_name)):
            trainer=HERE/('train_capacity_history.py' if selected=='capacity' else ('train_v2.py' if kind=='history' else 'train.py'))
            run(f'train-{output}',[sys.executable,trainer,'--kind',kind,'--parent',parent,
                '--output',HERE/output,'--data-scale','expanded','--device','mps','--fast-entities'])
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
    finally:
        base_service.terminate();base_service.wait(timeout=30)

if __name__=='__main__':main()
