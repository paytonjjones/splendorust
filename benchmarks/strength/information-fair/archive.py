#!/usr/bin/env python3
"""Lossless bounded-size chunks; preserve exact raw hashes and shard recovery."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from boundary import sha

def archive(directory):
    replay=json.loads((directory/'replay.json').read_text())
    raw=directory/'games.jsonl'
    assert replay['raw_sha256']==sha(raw)
    meta,*rows=map(json.loads,raw.read_text().splitlines())
    assert replay['checked_games']==len(rows)==meta['games']
    # Shards are exactly reconstructible from the merged header and ordered rows.
    shards=[]
    for index, header in enumerate(meta['shard_metadata']):
        start=2*header['offset_block']; stop=start+header['games']
        recovered=('\n'.join(map(json.dumps,[header]+rows[start:stop]))+'\n').encode()
        original=directory/f'shard-{index:02}.jsonl'
        assert recovered==original.read_bytes()
        shards.append(dict(file=original.name,raw_sha256=sha(original),start_index=start,games=header['games']))
    chunks=[]; recovered_hash=hashlib.sha256()
    with raw.open('rb') as handle:
        header=next(handle)
        for index,start in enumerate(range(0,len(rows),2500)):
            lines=[header] if index==0 else []
            lines += [next(handle) for _ in range(min(2500,len(rows)-start))]
            data=b''.join(lines)
            path=directory/f'games.part-{index:02}.jsonl.gz'
            if path.exists(): raise RuntimeError('archive already exists')
            path.write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
            assert gzip.decompress(path.read_bytes())==data
            assert path.stat().st_size<90_000_000
            recovered_hash.update(data)
            chunks.append(dict(file=path.name,archive_sha256=sha(path),raw_sha256=hashlib.sha256(data).hexdigest(),
                raw_bytes=len(data),archive_bytes=path.stat().st_size,games=len(lines)-(index==0)))
        assert not handle.read()
    assert recovered_hash.hexdigest()==sha(raw)
    manifest=dict(schema='information-fair-lossless-chunks-v1',raw_file=raw.name,raw_sha256=sha(raw),
        games=len(rows),chunks=chunks,shards=shards,
        restore='Concatenate gzip-decompressed chunks in listed order to recover games.jsonl exactly. Shard headers are in shard_metadata; select rows by start_index/games to recover each shard exactly.')
    (directory/'archives.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    print(json.dumps(archive(a.directory),indent=2))
if __name__=='__main__': main()
