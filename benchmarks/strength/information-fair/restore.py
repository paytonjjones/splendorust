#!/usr/bin/env python3
"""Recover the exact merged JSONL without changing checked-in archives."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from boundary import sha

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    manifest=json.loads((a.directory/'archives.json').read_text())
    digest=hashlib.sha256()
    with a.output.open('xb') as out:
        for part in manifest['chunks']:
            path=a.directory/part['file'];assert sha(path)==part['archive_sha256']
            data=gzip.decompress(path.read_bytes());assert hashlib.sha256(data).hexdigest()==part['raw_sha256']
            out.write(data);digest.update(data)
    assert digest.hexdigest()==manifest['raw_sha256']
    print('Recovered',manifest['games'],'games',digest.hexdigest())
if __name__=='__main__':main()
