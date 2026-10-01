#!/usr/bin/env python3
"""Audit frozen runtime, lossless histories, replay evidence and paired summaries."""
import gzip
import hashlib
import json
from pathlib import Path
from boundary import ROOT, ARMS, sha
from upstream import SOURCE
from summarize import summarize

BASE=Path(__file__).resolve().parent

def main():
    freeze=json.loads((BASE/'freeze.json').read_text())
    for name, expected in freeze['files'].items(): assert sha(ROOT/name)==expected, ('changed frozen file',name)
    for name, expected in freeze['upstream_files'].items(): assert sha(SOURCE/name)==expected, ('changed upstream file',name)
    counts=[]
    for stage in ['screen','confirmation']:
        for arm in ARMS:
            directory=BASE/stage/arm
            manifest=json.loads((directory/'archives.json').read_text())
            digest=hashlib.sha256(); lines=0
            for chunk in manifest['chunks']:
                path=directory/chunk['file'];assert sha(path)==chunk['archive_sha256']
                data=gzip.decompress(path.read_bytes());assert hashlib.sha256(data).hexdigest()==chunk['raw_sha256']
                assert len(data)==chunk['raw_bytes'];digest.update(data);lines+=data.count(b'\n')
            assert digest.hexdigest()==manifest['raw_sha256'] and lines==manifest['games']+1
            replay=json.loads((directory/'replay.json').read_text())
            assert replay['raw_sha256']==manifest['raw_sha256'] and replay['checked_games']==manifest['games']
            counts.append(dict(stage=stage,arm=arm,games=manifest['games'],transitions=replay['checked_transitions'],raw_sha256=manifest['raw_sha256']))
        # Retained ignored originals support a fresh exact summary rerun.
        assert summarize(BASE/stage)==json.loads((BASE/stage/'summary.json').read_text())
    result=dict(status='passed',frozen_revision=freeze['revision'],schedules=counts,
        games=sum(r['games'] for r in counts),transitions=sum(r['transitions'] for r in counts),
        scope='Frozen code/binaries/models/upstream; lossless archive hashes; complete replay counts; exact rerun of matched statistical summaries.')
    (BASE/'final-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
