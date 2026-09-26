#!/usr/bin/env python3
"""Compare pinned Rinascimento default data under every consistent suit mapping."""
import collections
import csv
import hashlib
import itertools
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = 'ce31592f78572096ceedd5ced1bac4f82c5f08db'


def main():
    checkout = pathlib.Path(sys.argv[1]).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(checkout), *args], text=True).strip()
    if git('rev-parse', 'HEAD') != COMMIT or git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('reference must be clean at the pinned commit')
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    colors = ['white', 'blue', 'green', 'red', 'black']
    with (ROOT / 'data/cards.csv').open() as stream:
        cards = collections.Counter((int(r['tier']), colors.index(r['bonus']), int(r['points']), *(int(r[c]) for c in colors)) for r in csv.DictReader(stream))
    with (ROOT / 'data/nobles.csv').open() as stream:
        nobles = collections.Counter((int(r['points']), *(int(r[c]) for c in colors)) for r in csv.DictReader(stream))
    paths = [checkout / f'assets/default/decks/{i}.csv' for i in range(1, 4)]
    paths.append(checkout / 'assets/default/nobles/nobles.csv')
    def read(path):
        rows = [tuple(map(int, line.split(','))) for line in path.read_text().splitlines() if line and not line.startswith('#')]
        if rows[0] != (len(rows) - 1, 5):
            raise ValueError('invalid data dimensions')
        return rows[1:]
    rows = [(tier, *r) for tier, path in enumerate(paths[:3], 1) for r in read(path)]
    noble_rows = read(paths[3])
    mappings = []
    for p in itertools.permutations(range(5)):
        mapped = collections.Counter((r[0], p[r[1]], r[2], *(r[3+p.index(i)] for i in range(5))) for r in rows)
        mapped_nobles = collections.Counter((r[0], *(r[1+p.index(i)] for i in range(5))) for r in noble_rows)
        mappings.append({'suit_to_local_color': [colors[i] for i in p], 'matched_cards': (cards & mapped).total(), 'matched_nobles': (nobles & mapped_nobles).total()})
    # UIStandards.java lists green, blue, red, white, black RGB colors.
    displayed = next(m for m in mappings if m['suit_to_local_color'] == ['green', 'blue', 'red', 'white', 'black'])
    source_paths = paths + [checkout / p for p in ['LICENSE', 'src/gui/UIStandards.java', 'src/game/Parameters.java', 'src/game/action/passive/TakeNoble.java', 'src/game/action/active/buy/BuyCard.java', 'src/game/action/active/reserve/deck/ReserveDeckCard.java']]
    print(json.dumps({'repository': 'https://github.com/ivanbravi/RinascimentoFramework', 'commit': COMMIT,
        'license': 'MIT, copyright 2021 Ivan Bravi', 'script_sha256': sha(pathlib.Path(__file__)),
        'source_files_sha256': {str(p.relative_to(checkout)): sha(p) for p in source_paths},
        'local_files_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / 'data/cards.csv', ROOT / 'data/nobles.csv']},
        'reference_card_count': len(rows), 'reference_noble_count': len(noble_rows),
        'displayed_mapping': displayed, 'best_card_match_count': max(m['matched_cards'] for m in mappings),
        'mapping_count': len(mappings),
        'card_match_histogram': dict(sorted(collections.Counter(m['matched_cards'] for m in mappings).items())),
        'best_mappings': [m for m in mappings if m['matched_cards'] == max(x['matched_cards'] for x in mappings)],
        'decision': 'Default data is not a standard-game baseline under any consistent suit mapping. No transition parity tested.'}, indent=2))


if __name__ == '__main__':
    main()
