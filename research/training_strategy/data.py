"""Versioned root-search data. Setup/decision fields are audit-only, never inputs."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/e95'))
from public_model import inputs

DTYPE = np.dtype([
    ('setup', '<u8'), ('decision', '<u4'), ('seat', 'u1'), ('full', 'u1'),
    ('padding', '<u2'), ('x', '<f4', (392,)), ('context', '<f4', (7,)),
    ('mask', '<f4', (81,)), ('visits', '<u4', (81,)), ('q', '<f4', (81,)),
    ('root', '<f4'), ('network', '<f4'), ('action', '<u2'),
    ('padding2', '<u2'), ('outcome', '<f4'),
])
assert DTYPE.itemsize == 2600


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    path = Path(path)
    assert path.stat().st_size > 0 and path.stat().st_size % DTYPE.itemsize == 0
    return np.memmap(path, mode='r', dtype=DTYPE)


def validate(rows):
    assert np.isfinite(rows['x']).all() and np.isfinite(rows['context']).all()
    assert np.isin(rows['mask'], [0, 1]).all()
    assert (rows['mask'].sum(-1) > 0).all()
    assert (rows['action'] < 81).all()
    assert (rows['mask'][np.arange(len(rows)), rows['action']] == 1).all()
    assert (rows['padding'] == 0).all() and (rows['padding2'] == 0).all()
    assert np.isin(rows['seat'], [0, 1]).all() and np.isin(rows['full'], [0, 1]).all()
    explored = rows['visits'] > 0
    assert np.array_equal(np.isfinite(rows['q']), explored)
    assert (rows['mask'][explored] == 1).all()
    assert ((rows['q'][explored] >= 0) & (rows['q'][explored] <= 1)).all()
    has_search = explored.any(-1)
    assert np.isfinite(rows['root'][has_search]).all()
    assert np.isfinite(rows['network'][has_search]).all()
    assert ((rows['root'][has_search] >= 0) & (rows['root'][has_search] <= 1)).all()
    counts = rows['visits'][has_search].astype(np.float64)
    means = (np.nan_to_num(rows['q'][has_search]) * counts).sum(-1) / counts.sum(-1)
    assert np.allclose(means, rows['root'][has_search], atol=1e-6, rtol=0)
    assert ((rows['full'] == 0) | has_search).all()
    finite = np.isfinite(rows['outcome'])
    assert np.isin(rows['outcome'][finite], [0, .5, 1]).all()
    eligible = finite & (rows['full'] == 1) & has_search
    return eligible


def prepare(directory):
    directory = Path(directory)
    rows = read(directory / 'rows.bin')
    eligible = validate(rows)
    source_hash = sha(directory / 'rows.bin')
    path = directory / 'inputs.bin'
    if not path.exists():
        tmp = directory / 'inputs.bin.partial'
        x = np.memmap(tmp, mode='w+', dtype='<f4', shape=(len(rows), 525))
        for i in range(0, len(rows), 4096):
            x[i:i+4096] = inputs(rows['x'][i:i+4096], rows['context'][i:i+4096], False)
        x.flush()
        del x
        tmp.rename(path)
    assert path.stat().st_size == len(rows) * 525 * 4
    visits = rows['visits'][eligible].astype(np.float64)
    policy = visits / visits.sum(-1, keepdims=True)
    entropy = -(policy * np.log(np.maximum(policy, 1e-300))).sum(-1)
    receipt = dict(schema='canonical-rich-root-v1', source=str(directory / 'rows.bin'),
        source_sha256=source_hash, inputs=str(path), inputs_sha256=sha(path),
        history_sha256=sha(directory / 'histories.jsonl'), rows=len(rows),
        eligible_rows=int(eligible.sum()), incomplete_rows=int((~np.isfinite(rows['outcome'])).sum()),
        non_full_or_no_search_rows=int((~eligible & np.isfinite(rows['outcome'])).sum()),
        setups=len(np.unique(rows['setup'])), policy_entropy=float(entropy.mean()),
        explored_actions_per_row=float((visits > 0).sum(-1).mean()),
        executed_vs_visit_argmax=float((rows['action'][eligible] == policy.argmax(-1)).mean()),
        profile='canonical-v2', learner_fields='public x, public context; audit IDs excluded')
    manifest = directory / 'data.json'
    if manifest.exists():
        assert json.loads(manifest.read_text()) == receipt, 'Existing data receipt differs'
    else:
        manifest.write_text(json.dumps(receipt, indent=2) + '\n')
    return rows, np.memmap(path, mode='r', dtype='<f4', shape=(len(rows), 525)), np.flatnonzero(eligible), receipt


if __name__ == '__main__':
    print(json.dumps(prepare(sys.argv[1])[3], indent=2))
