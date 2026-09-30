#!/usr/bin/env python3
"""Audit setup separation between training, development and final reports."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--train', action='append', default=[])
p.add_argument('--dev', action='append', default=[])
p.add_argument('--report', action='append', default=[])
p.add_argument('--row-bytes', action='append', default=[], help='PATH=1444 for older binary rows; default 1844')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
row_bytes = {name: int(size) for name, size in (spec.rsplit('=', 1) for spec in a.row_bytes)}


def dataset(path):
    path = Path(path)
    if path.suffix == '.bin':
        stride = row_bytes.get(str(path), 1844)
        if stride not in (1444, 1844, 2232) or path.stat().st_size % stride:
            raise ValueError(f'incomplete or unsupported binary dataset: {path}')
        rows = np.memmap(path, mode='r', dtype=np.dtype([('setup', '<u8'), ('rest', f'V{stride - 8}')]))
        return set(map(int, np.unique(rows['setup'])))
    with path.open() as f:
        return {int(json.loads(line)['setup']) for line in f}


def report(path):
    path = Path(path)
    if path.suffix == '.jsonl':
        with path.open() as f:
            metadata = json.loads(next(f))
            rows = [json.loads(line) for line in f]
        if len(rows) != metadata['games']:
            raise ValueError(f'unfinished external report: {path}')
        return {int(row['setup_seed']) for row in rows}
    result = json.loads(path.read_text())
    if len(result['records']) != result['requested_games']:
        raise ValueError(f'unfinished arena report: {path}')
    return {int(row['seed']) for row in result['records']}


groups = {}
evidence = []
for group, paths, reader in [('train', a.train, dataset), ('dev', a.dev, dataset), ('final', a.report, report)]:
    groups[group] = set()
    for name in paths:
        path = Path(name)
        ids = reader(path)
        groups[group].update(ids)
        sha = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                sha.update(chunk)
        evidence.append(dict(group=group, file=str(path), setups=len(ids), sha256=sha.hexdigest()))
intersections = {f'{left}/{right}': len(groups[left] & groups[right])
                 for left, right in [('train', 'dev'), ('train', 'final'), ('dev', 'final')]}
result = dict(files=evidence, distinct_setups={g: len(ids) for g, ids in groups.items()},
              intersections=intersections, passed=not any(intersections.values()))
a.output.write_text(json.dumps(result, indent=2) + '\n')
if not result['passed']:
    raise SystemExit('setup split overlap detected')
