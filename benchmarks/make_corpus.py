#!/usr/bin/env python3
"""Build mapped full-deck cases, and verify all functional external data tuples."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASK = (1 << 64) - 1
COLORS = ['white', 'blue', 'green', 'red', 'black']


class Rng:
    def __init__(self, seed):
        self.state = seed

    def next(self):
        self.state = (self.state + 0x9e3779b97f4a7c15) & MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & MASK
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & MASK
        return z ^ (z >> 31)

    def index(self, n):
        threshold = ((-n) & MASK) % n
        while True:
            value = self.next()
            if value >= threshold:
                return value % n

    def shuffle(self, values):
        for i in range(len(values) - 1, 0, -1):
            j = self.index(i + 1)
            values[i], values[j] = values[j], values[i]
        return values


def create(count, seed, external):
    cards = list(csv.DictReader((ROOT / 'data/cards.csv').open()))
    nobles = list(csv.DictReader((ROOT / 'data/nobles.csv').open()))
    card_map = []
    noble_map = []
    for c in cards:
        matches = [x['id'] for x in external['cards'] if
                   (int(c['tier']) - 1, COLORS.index(c['bonus']), int(c['points']), [int(c[k]) for k in COLORS]) ==
                   (x['tier'], x['bonus'], x['points'], x['cost'])]
        assert len(matches) == 1
        card_map += matches
    for n in nobles:
        matches = [x['id'] for x in external['nobles'] if
                   (int(n['points']), [int(n[k]) for k in COLORS]) == (x['points'], x['cost'])]
        assert len(matches) == 1
        noble_map += matches
    assert len(cards) == 90 and len(set(card_map)) == 90
    assert len(nobles) == 10 and len(set(noble_map)) == 10
    cases = []
    for i in range(count):
        case_seed = Rng((seed + i) & MASK).next()
        rng = Rng(case_seed)
        decks = [rng.shuffle(list(range(a, b))) for a, b in [(0, 40), (40, 70), (70, 90)]]
        chosen_nobles = sorted(rng.shuffle(list(range(10)))[:3])
        cases.append({'seed': case_seed, 'policy_seed': case_seed ^ 0xd1b54a32d192ed03, 'decks': decks, 'nobles': chosen_nobles})
    return {'schema_version': 1, 'profile': 'seal256-intersection-v1', 'master_seed': seed,
            'seed_schedule': 'SplitMix64(master+i).next; tier Fisher-Yates then noble Fisher-Yates; supplied array is draw order; policy_seed=seed XOR 0xd1b54a32d192ed03',
            'core_to_native_cards': card_map, 'core_to_native_nobles': noble_map, 'cases': cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--external-data', type=Path, default=ROOT / 'benchmarks/external/seal256-data.json')
    parser.add_argument('--count', type=int, default=64)
    parser.add_argument('--seed', type=int, default=930000001)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.count > 0 and 0 <= args.seed <= MASK
    corpus = create(args.count, args.seed, json.loads(args.external_data.read_text()))
    data = json.dumps(corpus, sort_keys=True, separators=(',', ':')).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(json.dumps({'count': args.count, 'file': str(args.output), 'sha256': hashlib.sha256(data).hexdigest(), 'card_data_matches': 90, 'noble_data_matches': 10}))


if __name__ == '__main__':
    main()
