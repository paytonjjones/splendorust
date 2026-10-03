"""Conservative paired native statistics, including caps-as-unknown sensitivity."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


def bound(blocks):
    radius = math.sqrt(math.log(40) / (2 * len(blocks)))
    return [max(0, sum(x[0] for x in blocks) / len(blocks) - radius),
            min(1, sum(x[1] for x in blocks) / len(blocks) + radius)]


def summarize(metadata, rows):
    if len(rows) != metadata['games'] or not rows or len(rows) % 2:
        raise ValueError('Require the full planned paired schedule')
    blocks = []
    sensitivity = []
    statuses = collections.Counter()
    terms = collections.Counter()
    seeds = set()
    for offset in range(0, len(rows), 2):
        pair = rows[offset:offset + 2]
        block = offset // 2
        if [r['index'] for r in pair] != [offset, offset + 1]:
            raise ValueError('Missing or unordered game index')
        if [r['rotation'] for r in pair] != [0, 1] or any(r['block'] != block for r in pair):
            raise ValueError('Invalid paired block')
        if pair[0]['setup_seed'] != pair[1]['setup_seed'] or pair[0]['setup_seed'] in seeds:
            raise ValueError('Duplicate or mismatched setup seed')
        seeds.add(pair[0]['setup_seed'])
        if pair[0]['initial_state'] != pair[1]['initial_state']:
            raise ValueError('Paired initial states differ')
        current = []
        caps_unknown = []
        for rotation, row in enumerate(pair):
            if row['seats'] != (['champion', 'alphazero'] if rotation == 0 else ['alphazero', 'champion']):
                raise ValueError('Candidate seat rotation differs')
            status = row['status']
            statuses[status] += 1
            terms[row.get('termination', 'unknown')] += 1
            if status == 'complete':
                rewards = row['rewards']
                if rewards is None or len(rewards) != 2 or any(x not in (0, .5, 1) for x in rewards) or sum(rewards) != 1:
                    raise ValueError('Invalid shared-win credit')
                credit = rewards[row['seats'].index('champion')]
                current.append((credit, credit))
            else:
                if row.get('rewards') is not None or row.get('native_rewards') is not None:
                    raise ValueError('Unknown game has an outcome')
                current.append((0, 1))
            caps_unknown.append((0, 1) if row.get('termination') == 'native_turn_cap' else current[-1])
        blocks.append(tuple(sum(x[i] for x in current) / 2 for i in (0, 1)))
        sensitivity.append(tuple(sum(x[i] for x in caps_unknown) / 2 for i in (0, 1)))
    rejected = []
    if statuses['no_legal_action'] / len(rows) > .01:
        rejected.append('more than one percent no-action')
    if any(count and key not in ('complete', 'no_legal_action') for key, count in statuses.items()):
        rejected.append('invalid, decision-limit, or unsupported status')
    interval = bound(blocks)
    caps_interval = bound(sensitivity)
    return dict(games=len(rows), setup_blocks=len(blocks), statuses=dict(statuses),
        terminal_categories=dict(terms),
        all_requested_credit_bounds=[sum(x[i] for x in blocks) / len(blocks) for i in (0, 1)],
        conservative_hoeffding95_missing_envelope=interval,
        caps_as_unknown_credit_bounds=[sum(x[i] for x in sensitivity) / len(sensitivity) for i in (0, 1)],
        caps_as_unknown_hoeffding95=caps_interval,
        radius=math.sqrt(math.log(40) / (2 * len(blocks))),
        evidence_rejections=rejected,
        decisive_native_criterion=not rejected and interval[0] > .55,
        decisive_with_caps_unknown=not rejected and caps_interval[0] > .55,
        scope='Native paired profile only. A final claim also requires a prior freeze, unchanged target, replay, source/binary/service identity, and fresh held-out seeds.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    raw = args.input.read_bytes()
    metadata, *rows = [json.loads(line) for line in raw.splitlines() if line]
    result = summarize(metadata, rows)
    result.update(raw_sha256=hashlib.sha256(raw).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
