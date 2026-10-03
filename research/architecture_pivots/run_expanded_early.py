"""Run registered completed native models while the entity fit continues."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'expanded-early'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'plan.json').write_text(json.dumps(dict(kinds=['small','small-cold','capacity'],
        native_master=5190000000,canonical_master=5180000000,games=2000,
        scheduling_only=True,shared_load='Concurrent expanded entity training',
        script_sha256=sha(Path(__file__))),indent=2)+'\n')
    def run(name,command,env=None,allowed=(0,)):
        with (OUT/f'{name}.log').open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode in allowed,f'{name}: {result.returncode}'
        (OUT/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    run('worker-build',['cargo','build','--release','--locked','--package','splendor-arena','--example','native_policy_worker'])
    binary=OUT/'native_policy_worker.bin';binary.write_bytes((ROOT/'target/release/examples/native_policy_worker').read_bytes());binary.chmod(0o755)
    champion=ROOT/'research/e81/model/model.bin'
    (OUT/'host-start.json').write_text(json.dumps(dict(activity=subprocess.check_output(['ps','-axo','pid,pcpu,pmem,etime,comm'],text=True)))+'\n')
    for index,kind in enumerate(('small','small-cold','capacity')):
        checkpoint=HERE/f'expanded-{kind}/model.pt'
        manifest=json.loads(checkpoint.with_name('manifest.json').read_text())
        assert len(manifest['history'])==manifest['epochs']==12 and sha(checkpoint)==manifest['checkpoint_sha256']
        command=[sys.executable,HERE/'export.py',checkpoint,'--port',19534,'--slot',10+index]
        if kind=='capacity':command+=['--native-capacity']
        run(f'export-{kind}',command)
        model=checkpoint.with_name('native-model.bin' if kind=='capacity' else 'model.bin')
        name=f'expanded-native-{kind}-champion'
        run(name,[sys.executable,HERE/'native_match.py','--model-a',model,'--model-b',champion,'--binary',binary,
            '--iterations-a',0,'--iterations-b',0,'--games',2000,'--master',5190000000,'--workers',14,'--output',HERE/name])
        name=f'expanded-{kind}-gate';directory=HERE/name
        env=os.environ.copy();env.update(SPLENDOR_CANDIDATE_MODEL=str(model),SPLENDOR_BEST_MODEL=str(champion))
        run(name,[sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-gumbel-candidate','--baseline','flywheel-gumbel',
            '--screen',2000,'--confirm',0,'--seed',5180000000,'--threads',32,'--iterations',128,'--depth',16,'--output',directory],env,(0,2))
        decision=json.loads((directory/'decision.json').read_text());assert 'raw_report_sha256' in decision
        build=json.loads((directory/'build.json').read_text());frozen=directory/'splendor.bin'
        frozen.write_bytes(Path(build['executable']).read_bytes());frozen.chmod(0o755);assert sha(frozen)==build['binary_sha256']
        (directory/'inference-manifest.json').write_text(json.dumps(dict(candidate=str(model),candidate_sha256=sha(model),
            baseline=str(champion),baseline_sha256=sha(champion),binary_sha256=sha(frozen),services=[],
            shared_load='Concurrent expanded entity training',environment={k:env[k] for k in ('SPLENDOR_CANDIDATE_MODEL','SPLENDOR_BEST_MODEL')}),indent=2)+'\n')
    (OUT/'complete.json').write_text(json.dumps(dict(registered_completed_base_screens=True))+'\n')

if __name__=='__main__':main()
