#!/usr/bin/env python3
"""Unpatched lyquentxy scheduled-draw feasibility probe, not a game benchmark.

The helper returns a native random_seed that chooses a requested remaining-card
index through the existing deterministic draw API. It does not rewrite rules.
"""
import argparse
import json
import math
from pathlib import Path
import sys

MULTIPLIER = 4594591


def native_draw_seed(remaining_index, remaining_count, packed_bitsets):
    if not 0 <= remaining_index < remaining_count:
        raise ValueError('requested remaining-card index is out of range')
    if math.gcd(MULTIPLIER, remaining_count) != 1:
        raise ValueError('native draw cannot select every remaining-card index')
    state_hash = sum((int(bits) & 255) * (1 << (5 * color))
                     for color, bits in enumerate(packed_bitsets))
    seed = (pow(MULTIPLIER, -1, remaining_count) * remaining_index - state_hash) % remaining_count
    # Zero selects the unrelated random branch in the native API.
    return seed if seed else remaining_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    import numpy as np
    from splendor.SplendorLogicNumba import Board, my_packbits
    from splendor.SplendorLogic import np_all_cards_1, np_all_cards_2, np_all_cards_3
    board = Board(2)
    baseline = board.get_state().copy()
    checks = 0
    for tier, cards in enumerate((np_all_cards_1, np_all_cards_2, np_all_cards_3)):
        per_color = len(cards[0])
        full_bits = int(my_packbits(np.ones(per_color, dtype=np.int8)))
        fixture = baseline.copy()
        fixture[25 + 2 * tier, :5] = per_color
        fixture[26 + 2 * tier, :5] = np.asarray(full_bits, dtype=np.uint8).view(np.int8)
        for target in range(5 * per_color):
            board.copy_state(fixture, True)
            seed = native_draw_seed(target, 5 * per_color, fixture[26 + 2 * tier, :5])
            result = board._get_deck_card(tier, seed)
            color, card_index = divmod(target, per_color)
            assert np.array_equal(result, cards[color][card_index])
            checks += 1
    all_counts = all(math.gcd(MULTIPLIER, n) == 1 for n in range(1, 41))
    assert all_counts
    result = {'probe': 'lyquentxy_native_scheduled_draw_v1', 'all_counts_1_to_40_invertible': all_counts,
              'native_full_deck_draw_checks': checks, 'upstream_patches': [],
              'limits': ['Does not certify dataset equality, setup conversion, complete turn parity or rule alignment.',
                         'Native random_seed is chosen by adapter for scheduled refill; no policy RNG is used.']}
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n')
    print(rendered)


if __name__ == '__main__':
    main()
