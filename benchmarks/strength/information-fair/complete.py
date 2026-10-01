#!/usr/bin/env python3
"""Complete the frozen protocol, then save and audit all evidence."""
import gzip
import json
import subprocess
from pathlib import Path
from boundary import ROOT, ARMS, sha

BASE = Path(__file__).resolve().parent
PYTHON = ROOT / 'local/strength/inference/bin/python'


def status(step):
    (BASE/'finish-status.json').write_text(json.dumps(dict(step=step),indent=2)+'\n')
    print(step,flush=True)


def check_interrupted():
    manifest=json.loads((BASE/'interrupted/control/interruption.json').read_text())
    count=0
    for entry in manifest['files']:
        archive=BASE/'interrupted/control'/entry['archive']
        assert sha(archive)==entry['archive_sha256']
        original=gzip.decompress(archive.read_bytes())
        assert __import__('hashlib').sha256(original).hexdigest()==entry['raw_sha256']
        old_meta,*old_rows=map(json.loads,original.splitlines())
        with (BASE/'confirmation/control'/entry['file']).open() as handle:
            new_meta=json.loads(next(handle))
            for key in ['master','offset_block','games','model_sha256','policy_binary_sha256','source_sha256','external_config','iterations','depth','world_pool','gumbel_config']:
                assert old_meta[key]==new_meta[key],('restart setting differs',key)
            for old in old_rows:
                new=json.loads(next(handle))
                # Real elapsed times can change with host load. All decisions,
                # random streams, work counts, inputs and outcomes must match.
                for key in ['elapsed_seconds','policy_seconds']:
                    old.pop(key);new.pop(key)
                assert old==new,('interrupted game differs',old['index'])
                count+=1
        assert len(old_rows)==entry['complete_games']
    assert count==manifest['complete_games']
    result=dict(status='passed',checked_games=count,
        scope='Every completed interrupted game matches the full repeated control schedule in all non-timing fields. No completed result was selected or dropped.')
    (BASE/'interruption-verification.json').write_text(json.dumps(result,indent=2)+'\n')


def run(script,args=(),log=None,append=False):
    with (BASE/(log or script.replace('.py','.log'))).open('a' if append else 'w') as out:
        subprocess.run([PYTHON,BASE/script,*args],stdout=out,stderr=subprocess.STDOUT,check=True,cwd=ROOT)


def main():
    try:
        status('running frozen protocol')
        run('protocol.py',log='protocol.log',append=True)
        assert json.loads((BASE/'progress.json').read_text())==dict(status='complete')
        status('checking interrupted control repeat')
        check_interrupted()
        for arm in ARMS:
            status('archiving confirmation '+arm)
            directory=BASE/'confirmation'/arm
            if not (directory/'archives.json').exists():
                run('archive.py',[directory],log='confirmation/'+arm+'/archive.log')
        status('auditing all fixed schedules')
        run('audit.py',log='final-audit.log')
        status('writing report')
        run('report.py',log='report.log')
        paths=sorted(p for p in BASE.rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix!='.jsonl'
            and p.name not in ['artifact-manifest.json','finish-status.json','completion-driver.log','completion-process.json'])
        manifest=dict(schema='information-fair-final-artifacts-v1',
            files={str(p.relative_to(BASE)):sha(p) for p in paths})
        (BASE/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        status('complete; report and evidence ready for review')
    except Exception as error:
        status('failed: '+str(error))
        raise


if __name__=='__main__':main()
