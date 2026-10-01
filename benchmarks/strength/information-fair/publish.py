#!/usr/bin/env python3
"""Publish only complete, audited evidence; preserve failures for review."""
import json
import subprocess
import time
from pathlib import Path
from boundary import ROOT, sha

BASE=Path(__file__).resolve().parent
LOCAL=ROOT/'local/strength/information-fair-publication'
PYTHON=ROOT/'local/strength/inference/bin/python'
BRANCH='codex/information-fair-alphazero'


def status(step,**details):
    result=dict(step=step,**details)
    (LOCAL/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


def command(args):
    print('RUN',*map(str,args),flush=True)
    try:
        return subprocess.check_output(list(map(str,args)),cwd=ROOT,stderr=subprocess.STDOUT,text=True)
    except subprocess.CalledProcessError as error:
        print(error.output,flush=True)
        raise


def check_artifacts():
    assert json.loads((BASE/'progress.json').read_text())==dict(status='complete')
    audit=json.loads((BASE/'final-audit.json').read_text())
    assert audit['status']=='passed' and audit['games']==66000
    assert json.loads((BASE/'interruption-verification.json').read_text())['checked_games']==4180
    manifest=json.loads((BASE/'artifact-manifest.json').read_text())
    for name,expected in manifest['files'].items():
        assert sha(BASE/name)==expected,('changed saved artifact',name)
    assert 'Status: complete.' in (BASE/'REPORT.md').read_text()
    assert command(['git','branch','--show-current']).strip()==BRANCH


def main():
    LOCAL.mkdir(parents=True,exist_ok=True)
    try:
        status('waiting for the complete audited report')
        while True:
            try: finish=json.loads((BASE/'finish-status.json').read_text())['step']
            except (FileNotFoundError,json.JSONDecodeError): finish='waiting'
            if finish.startswith('failed:'): raise RuntimeError(finish)
            if finish=='complete; report and evidence ready for review': break
            # This wait is in the detached helper, not a blocking tool call.
            time.sleep(30)
        status('checking all final artifacts')
        check_artifacts()
        changed=command(['git','status','--porcelain','--untracked-files=all']).splitlines()
        assert all(line[3:].startswith('benchmarks/strength/information-fair/') for line in changed),changed
        readme=ROOT/'README.md'
        text=readme.read_text()
        old='[information-fair AlphaZero comparison](benchmarks/strength/information-fair/README.md)'
        new='[information-fair AlphaZero comparison](benchmarks/strength/information-fair/REPORT.md)'
        assert old in text
        readme.write_text(text.replace(old,new))
        print(command(['git','add','README.md','benchmarks/strength/information-fair']),flush=True)
        print(command(['git','diff','--cached','--check']),flush=True)
        print(command(['git','commit','-m','Report information-fair AlphaZero confirmation']),flush=True)
        # Normal push rejects concurrent main updates. Each retry integrates
        # main and rechecks the frozen runtime and every saved artifact.
        for attempt in range(3):
            status('integrating main',attempt=attempt+1)
            print(command(['git','pull','--no-rebase','--no-edit','origin','main']),flush=True)
            check_artifacts()
            print(command([PYTHON,BASE/'audit.py']),flush=True)
            # An identical audit rerun must leave the committed report intact.
            assert not command(['git','status','--porcelain']).strip(),'integration changed saved evidence'
            status('pushing main',attempt=attempt+1)
            pushed=subprocess.run(['git','push','origin','HEAD:main'],cwd=ROOT,text=True,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            print(pushed.stdout,flush=True)
            if pushed.returncode==0:
                head=command(['git','rev-parse','HEAD']).strip()
                remote=command(['git','ls-remote','origin','refs/heads/main']).split()[0]
                assert head==remote,('remote verification differs',head,remote)
                status('pushed and verified',commit=head,games=66000,
                    report=str(BASE/'REPORT.md'),artifact_manifest_sha256=sha(BASE/'artifact-manifest.json'))
                return
            if 'non-fast-forward' not in pushed.stdout and 'fetch first' not in pushed.stdout:
                raise RuntimeError('push failed; see retained publication log')
        raise RuntimeError('main changed during all three publication attempts')
    except Exception as error:
        status('failed',reason=str(error))
        raise


if __name__=='__main__':main()
