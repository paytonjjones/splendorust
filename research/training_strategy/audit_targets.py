"""Check terminal labels against retained games and measure search-label content."""
import argparse
import json
from pathlib import Path

import numpy as np

from data import prepare, sha


def audit(directory):
    directory = Path(directory).resolve()
    rows, _, eligible, receipt = prepare(directory)
    completion = json.loads((directory / 'complete.json').read_text())
    records = [json.loads(line) for line in
               (directory / 'histories.jsonl').read_text().splitlines()]
    assert len(records) == completion['games']
    assert [record['game'] for record in records] == list(range(len(records)))
    counts = dict(complete=0, no_legal_action=0, decision_limit=0)
    start = 0
    for record in records:
        counts[record['status']] += 1
        game_rows = rows[start:start + record['rows']]
        start += record['rows']
        assert len(game_rows) == record['rows']
        assert (game_rows['setup'] == record['history']['seed']).all()
        assert (game_rows['decision'] < len(record['history']['actions'])).all()
        assert (np.diff(game_rows['decision'].astype(np.int64)) > 0).all()
        assert int(game_rows['full'].sum()) == record['full_rows']
        if record['status'] == 'complete':
            winners = record['winners']
            assert winners in (1, 2, 3)
            expected = np.array([
                1 / winners.bit_count() if winners & (1 << int(seat)) else 0
                for seat in game_rows['seat']
            ], dtype=np.float32)
            assert np.array_equal(expected, game_rows['outcome'])
        else:
            assert record['winners'] == 0
            assert np.isnan(game_rows['outcome']).all()
    assert start == len(rows) == completion['rows']
    assert list(counts.values()) == completion['counts']
    assert sum(record['simulations'] for record in records) == completion['simulations']
    assert sum(record['inferences'] for record in records) == completion['inferences']
    assert len(eligible) > 0
    selected = rows[eligible]
    visits = selected['visits'].astype(np.float64)
    explored = visits > 0
    policy = visits / visits.sum(-1, keepdims=True)
    legal_counts = selected['mask'].sum(-1)
    explored_counts = explored.sum(-1)
    q = np.where(explored, selected['q'], np.nan)
    spans = np.nanmax(q, axis=-1) - np.nanmin(q, axis=-1)
    outcome = selected['outcome']
    # These are correlated positions from a pilot, not held-out strength evidence.
    result = dict(
        schema='search-target-audit-v1', directory=str(directory), receipt=receipt,
        completion_sha256=sha(directory / 'complete.json'),
        history_sha256=sha(directory / 'histories.jsonl'),
        terminal_labels_match_records=True, counts=counts,
        rows=len(rows), eligible_rows=len(eligible),
        full_visit_totals=sorted(int(n) for n in np.unique(visits.sum(-1))),
        mean_executed_action_mass=float(policy[np.arange(len(policy)), selected['action']].mean()),
        mean_alternative_action_mass=float((1 - policy.max(-1)).mean()),
        mean_legal_actions=float(legal_counts.mean()),
        mean_explored_actions=float(explored_counts.mean()),
        mean_unexplored_legal_actions=float((legal_counts - explored_counts).mean()),
        mean_explored_q_span=float(spans.mean()),
        root_terminal_brier=float(np.mean((selected['root'] - outcome) ** 2)),
        network_terminal_brier=float(np.mean((selected['network'] - outcome) ** 2)),
        root_network_mse=float(np.mean((selected['root'] - selected['network']) ** 2)),
        eligible_rows_per_collection_hour=len(eligible) / (completion['seconds'] / 3600),
        collection_seconds=completion['seconds'],
        limits=['Position-weighted in-sample label diagnostics are not playing strength.',
                'Unexplored legal actions have no Q target.',
                'Pilot games are excluded from model training and evaluation.'])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('receipt', 'directory', 'limits')}, indent=2))


if __name__ == '__main__':
    main()
