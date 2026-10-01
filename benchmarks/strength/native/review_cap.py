#!/usr/bin/env python3
"""Review every native turn-cap case without rerunning either policy."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
from upstream import Upstream, Tracker

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    upstream = Upstream()
    cases = []
    for name in ['screen', 'confirmation', 'higher-search']:
        with (BASE / name / 'games.jsonl').open() as stream:
            metadata = json.loads(next(stream))
            for line in stream:
                record = json.loads(line)
                if record.get('termination') != 'native_turn_cap':
                    continue
                state = upstream.np.asarray(record['initial_state'], dtype=upstream.np.int8)
                tracker = Tracker(upstream, state)
                current = 0
                last_decisions = []
                for turn, (action, chance, digest) in enumerate(zip(
                        record['actions'], record['chance_seeds'], record['state_sha256'])):
                    legal = upstream.legal(state, current)
                    assert action in legal
                    if turn >= record['turns'] - 4:
                        observation = tracker.snapshot(state, current)
                        last_decisions.append(dict(turn=turn, seat=current,
                            identity=record['seats'][current], action=action,
                            legal_actions=legal, bank=observation['bank'],
                            hand_counts=[sum(player['tokens']) for player in observation['players']],
                            reserved_counts=[player['reserved_count'] for player in observation['players']],
                            scores=[upstream.game.getScore(state, i) for i in range(2)]))
                    child, next_seat = upstream.apply(state, current, action, chance)
                    tracker.update(state, child, current, action)
                    state, current = child, next_seat
                    assert hashlib.sha256(state.tobytes()).hexdigest() == digest
                reward = upstream.rewards(state, current)
                assert record['status'] == 'complete' and record['turns'] == 124
                assert record['scores'] == [upstream.game.getScore(state, i) for i in range(2)]
                assert max(record['scores']) < 15 and reward == record['native_rewards']
                cases.append(dict(schedule=name,
                    **{key: record[key] for key in ['index', 'block', 'rotation', 'setup_seed',
                        'seats', 'turns', 'scores', 'native_rewards', 'rewards', 'status']},
                    pass_counts={identity: sum(action == 80 and record['seats'][turn % 2] == identity
                        for turn, action in enumerate(record['actions'])) for identity in record['seats']},
                    last_decisions=last_decisions,
                    source_of_result='Unchanged upstream getGameEnded; native turn-cap result, not canonical'))
    summary = json.loads((BASE / 'confirmation/summary.json').read_text())
    main_cases = [case for case in cases if case['schedule'] == 'confirmation']
    credit_on_cap = sum(case['rewards'][case['seats'].index('champion')] for case in main_cases)
    low = (summary['candidate_credit_total'] - credit_on_cap) / summary['games']
    high = low + len(main_cases) / summary['games']
    radius = math.sqrt(math.log(2 / .05) / (2 * summary['setup_blocks']))
    result = dict(cases=cases, all_native_rewards_rechecked=True,
        primary_cap_as_unknown_sensitivity=dict(all_requested_credit_bounds=[low, high],
            conservative_hoeffding95=[max(0, low - radius), min(1, high + radius)],
            note='Hypothetical sensitivity only. Registered native protocol includes these legitimate upstream results.'),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
