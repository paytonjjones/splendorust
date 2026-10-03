"""Describe corpus size and policy diversity without treating rows as games."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'research'))
sys.path.insert(0, str(ROOT/'research/e95'))
from flywheel_model import DTYPE
from history_data import AUX


def summarize(data, split, native):
    setups = set()
    histogram = np.zeros(81, dtype=np.int64)
    rows_count = entropy = support = hidden_positions = hidden_targets = blind_draws = 0
    for index, entry in enumerate(data[split]):
        if entry['native'] != native:
            continue
        rows = np.memmap(entry['source'], mode='r', dtype=DTYPE)
        setups.update(map(int, np.unique(rows['setup'])))
        base = Path(entry.get('aux_base', ROOT/'local/research/architecture-pivots'/f'{split}-{index:02d}'))
        aux = np.memmap(str(base)+'.aux.bin', mode='r', dtype=AUX)
        assert len(aux) == len(rows) == entry['rows']
        starts = np.r_[0, np.flatnonzero(rows['setup'][1:] != rows['setup'][:-1])+1]
        ends = np.r_[starts[1:]-1, len(rows)-1]
        assert (ends > starts).all()
        assert (aux['opponent'][ends] == -1).all()
        assert (aux['opponent'] >= 0).sum() == len(rows)-len(starts)
        history = np.memmap(ROOT/'local/research/architecture-pivots/history-v2'/f'{split}-{index:03d}.history.bin',
                            mode='r', dtype='<f4', shape=(len(rows), 16, 32))
        first_events = np.array(history[starts+1, -1])
        assert (first_events[:, 0] == 1).all() and (first_events[:, 31] == 0).all()
        # Every recorded two-player decision switches actor. Next-opponent labels
        # cover executed actions after the first; the next prefix covers the first.
        blind_draws += int(((aux['opponent'] >= 24) & (aux['opponent'] < 27)).sum())
        blind_draws += int((first_events[:, 4] == 1).sum())
        hidden_positions += int((aux['belief'] >= 0).any(axis=1).sum())
        hidden_targets += int((aux['belief'] >= 0).sum())
        for start in range(0, len(rows), 4096):
            policy = np.array(rows['policy'][start:start+4096], dtype=np.float64)
            assert np.isfinite(policy).all()
            entropy -= float((policy*np.log(np.maximum(policy, 1e-30))).sum())
            support += int((policy > 0).sum())
            histogram += np.bincount(policy.argmax(axis=1), minlength=81)
        rows_count += len(rows)
    return dict(rows=rows_count, distinct_setups=len(setups), rows_per_setup=rows_count/len(setups),
                distinct_blind_draw_actions=blind_draws,
                blind_draw_policy_targets=int(histogram[24:27].sum()),
                mean_policy_entropy_nats=entropy/rows_count, mean_positive_policy_actions=support/rows_count,
                policy_argmax_actions_observed=int((histogram > 0).sum()), policy_argmax_counts=histogram.tolist(),
                positions_with_hidden_reservation=hidden_positions, hidden_reservation_targets=hidden_targets)


def main():
    result = dict(scope='Descriptive row statistics. Setup blocks are the independent game units. '
                  'Policy targets are single teacher actions; canonical opening sampling can execute another action. '
                  'Actual blind draws use executed next-opponent labels plus each first public event; native indices 24..26. '
                  'Hidden targets count occupied blind slots at observed positions, not distinct blind draws.', corpora={})
    for scale, filename in [('initial', 'data.json'), ('expanded', 'expanded-data.json')]:
        path = ROOT/'local/research/architecture-pivots'/filename
        data = json.loads(path.read_text())
        result['corpora'][scale] = dict(registry_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            splits={split: {profile: summarize(data, split, native)
                           for profile, native in [('native', True), ('canonical', False)]}
                    for split in ['train', 'dev']})
    (HERE/'data-summary.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
