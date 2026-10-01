#!/usr/bin/env python3
"""Lossless, deterministic gzip archives with both compressed and raw hashes."""
import gzip
import hashlib
import json
from pathlib import Path

def main():
    base=Path(__file__).resolve().parent
    missing=[str(path.relative_to(base)) for path in base.rglob('*.jsonl.gz')
             if not path.with_suffix('').exists()]
    if missing:
        raise FileNotFoundError('Restore all original raw files before refreshing archives: '+', '.join(missing))
    records=[]
    for source in sorted(base.rglob('*.jsonl')):
        raw=source.read_bytes()
        target=source.with_suffix(source.suffix+'.gz')
        packed=gzip.compress(raw,compresslevel=9,mtime=0)
        target.write_bytes(packed)
        assert gzip.decompress(target.read_bytes())==raw
        lines=raw.splitlines();meta=json.loads(lines[0])
        records.append(dict(path=str(target.relative_to(base)),gzip_sha256=hashlib.sha256(packed).hexdigest(),
            raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),gzip_bytes=len(packed),
            requested_games=meta['games'],recorded_games=len(lines)-1,full_schedule=len(lines)-1==meta['games']))
    (base/'archive-index.json').write_text(json.dumps(dict(format='gzip level9 mtime0; lossless raw JSONL',files=records),indent=2)+'\n')
if __name__=='__main__':main()
