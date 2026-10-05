from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

from adapter import (
    AHINLENDOR_NOBLE_TO_CANONICAL, AdapterError, BoardView, CanonicalAction, ReservedSlot,
    canonical_payment_for_ahin, complete_return, map_action,
    card_id_from_ahin, card_id_to_ahin, noble_id_to_ahin,
)

ROOT = Path(__file__).resolve().parents[3]
AHIN = ROOT / "local/strength/external/ahinlendor"


def rust_cards() -> list[tuple[int, int, int, tuple[int, ...]]]:
    text = (ROOT / "crates/splendor-core/src/data.rs").read_text()
    section = text.split("pub const CARDS: [Card; 90] = [", 1)[1].split("];", 1)[0]
    return [
        (int(m[1]) + 1, int(m[3]), int(m[2]), tuple(map(int, m[4].split(","))))
        for m in re.finditer(
            r"Card\s*\{\s*tier:\s*(\d+),\s*bonus:\s*(\d+),\s*points:\s*(\d+),\s*cost:\s*\[([^]]+)\]",
            section,
            re.S,
        )
    ]


def ahin_cards() -> list[tuple[int, int, int, tuple[int, ...]]]:
    text = (AHIN / "game_logic.cpp").read_text()
    section = text.split("static const std::vector<Card> standard_cards = {", 1)[1].split("};", 1)[0]
    colors = {"White": 0, "Blue": 1, "Green": 2, "Red": 3, "Black": 4}
    return [
        (int(m[2]), int(m[3]), colors[m[4]], tuple(map(int, m[5].split(",")))[:5])
        for m in re.finditer(
            r"Card\{\s*(\d+),\s*(\d+),\s*(\d+),\s*Color::(\w+),\s*Tokens\{([^}]+)\}\s*\}",
            section,
        )
    ]


def rust_nobles() -> list[tuple[int, ...]]:
    text = (ROOT / "crates/splendor-core/src/data.rs").read_text()
    section = text.split("pub const NOBLES: [[u8; 5]; 10] = [", 1)[1].split("];", 1)[0]
    return [tuple(map(int, row.split(","))) for row in re.findall(r"\[([^]]+)\]", section)]


def ahin_nobles() -> list[tuple[int, ...]]:
    text = (AHIN / "game_logic.cpp").read_text()
    section = text.split("static const std::vector<Noble> standard_nobles = {", 1)[1].split("};", 1)[0]
    return [
        tuple(map(int, m.split(",")))[:5]
        for m in re.findall(r"Noble\{\s*\d+,\s*\d+,\s*Tokens\{([^}]+)\}\s*\}", section)
    ]


class AdapterTests(unittest.TestCase):
    def test_pinned_checkout_and_card_id_conversion(self):
        import subprocess

        revision = subprocess.check_output(["git", "-C", AHIN, "rev-parse", "HEAD"], text=True).strip()
        from adapter import PINNED_AHINLENDOR_REVISION
        self.assertEqual(revision, PINNED_AHINLENDOR_REVISION)
        self.assertEqual([card_id_from_ahin(card_id_to_ahin(i)) for i in range(90)], list(range(90)))

    def test_all_90_cards_match_pinned_source_one_to_one(self):
        rust, ahin = rust_cards(), ahin_cards()
        self.assertEqual(len(rust), 90)
        self.assertEqual(len(ahin), 90)
        self.assertEqual(rust, ahin)

    def test_all_10_nobles_match_by_signature_not_id(self):
        rust, ahin = rust_nobles(), ahin_nobles()
        self.assertEqual(len(rust), 10)
        self.assertEqual(len(ahin), 10)
        self.assertEqual(sorted(rust), sorted(ahin))
        by_signature = {sig: idx + 1 for idx, sig in enumerate(ahin)}
        self.assertEqual(tuple(by_signature[sig] for sig in rust), (9, 8, 10, 6, 7, 5, 4, 2, 3, 1))
        self.assertEqual(tuple(noble_id_to_ahin(i) for i in range(10)), (9, 8, 10, 6, 7, 5, 4, 2, 3, 1))
        self.assertEqual(tuple(noble_id_to_ahin(i) for i in AHINLENDOR_NOBLE_TO_CANONICAL), tuple(range(1, 11)))

    def test_opponent_blind_identity_is_rejected(self):
        with self.assertRaisesRegex(AdapterError, "not observable"):
            BoardView((None,) * 12, (), (ReservedSlot(17, 1, False),), (), (0, 0, 0, 0, 0, 0))

    def test_market_buy_and_reserve_use_tier_major_slots(self):
        view = BoardView(tuple(range(12)), (20, 21, 22), (), (0, 1, 2), (1, 1, 1, 1, 1, 0))
        legal = {CanonicalAction("buy_visible", (4,)), CanonicalAction("buy_reserved", (2,)),
                 CanonicalAction("reserve_visible", (7,)), CanonicalAction("reserve_deck", (2,))}
        self.assertEqual(map_action(4, view, legal), CanonicalAction("buy_visible", (4,)))
        self.assertEqual(map_action(14, view, legal), CanonicalAction("buy_reserved", (2,)))
        self.assertEqual(map_action(22, view, legal), CanonicalAction("reserve_visible", (7,)))
        self.assertEqual(map_action(29, view, legal), CanonicalAction("reserve_deck", (2,)))

    def test_all_card_and_deck_action_indices(self):
        view = BoardView(tuple(range(12)), (20, 21, 22), (), (), (1, 1, 1, 1, 1, 0))
        legal = {
            *(CanonicalAction("buy_visible", (i,)) for i in range(12)),
            *(CanonicalAction("buy_reserved", (i,)) for i in range(3)),
            *(CanonicalAction("reserve_visible", (i,)) for i in range(12)),
            *(CanonicalAction("reserve_deck", (i,)) for i in range(3)),
        }
        for i in range(12):
            self.assertEqual(map_action(i, view, legal), CanonicalAction("buy_visible", (i,)))
            self.assertEqual(map_action(15 + i, view, legal), CanonicalAction("reserve_visible", (i,)))
        for i in range(3):
            self.assertEqual(map_action(12 + i, view, legal), CanonicalAction("buy_reserved", (i,)))
            self.assertEqual(map_action(27 + i, view, legal), CanonicalAction("reserve_deck", (i,)))

    def test_all_take_actions_map_to_expected_vectors(self):
        view = BoardView(tuple(range(12)), (), (), (), (4, 4, 4, 4, 4, 0))
        vectors = [
            (1, 1, 1, 0, 0), (1, 1, 0, 1, 0), (1, 1, 0, 0, 1),
            (1, 0, 1, 1, 0), (1, 0, 1, 0, 1), (1, 0, 0, 1, 1),
            (0, 1, 1, 1, 0), (0, 1, 1, 0, 1), (0, 1, 0, 1, 1),
            (0, 0, 1, 1, 1),
        ] + [tuple(2 if j == i else 0 for j in range(5)) for i in range(5)] + [
            tuple(int(j in pair) for j in range(5))
            for pair in ((0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3),
                         (1, 4), (2, 3), (2, 4), (3, 4))
        ] + [tuple(int(j == i) for j in range(5)) for i in range(5)]
        legal = {CanonicalAction("take", vector) for vector in vectors}
        self.assertEqual(len(vectors), 30)
        for index, vector in zip(range(30, 60), vectors):
            self.assertEqual(map_action(index, view, legal), CanonicalAction("take", vector))

    def test_returns_accumulate_to_one_legal_compound_action(self):
        view = BoardView(tuple(range(12)), (), (), (), (2, 2, 3, 1, 2, 2))
        legal = {CanonicalAction("return", (1, 0, 0, 0, 0, 1)),
                 CanonicalAction("return", (0, 1, 0, 0, 0, 1)),
                 CanonicalAction("return", (1, 1, 0, 0, 0, 0))}
        self.assertEqual(map_action(61, view, legal), CanonicalAction("return_token", (0,)))
        self.assertEqual(complete_return(view, (0, 1), legal), CanonicalAction("return", (1, 1, 0, 0, 0, 0)))
        with self.assertRaises(AdapterError):
            complete_return(view, (0,), legal)

    def test_noble_choice_uses_mapped_public_slot_order(self):
        view = BoardView(tuple(range(12)), (), (), (8, 0, 5), (0, 0, 0, 0, 0, 0))
        legal = {CanonicalAction("noble", (n,)) for n in view.noble_ids}
        for slot, noble_id in enumerate(view.noble_ids):
            self.assertEqual(map_action(66 + slot, view, legal), CanonicalAction("noble", (noble_id,)))

    def test_all_sequential_return_colors_have_neutral_intents(self):
        view = BoardView(tuple(range(12)), (), (), (), (2, 2, 2, 2, 2, 2))
        legal = {
            CanonicalAction("return", tuple(int(i in pair) for i in range(6)))
            for pair in ((0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (1, 3),
                         (1, 4), (2, 3), (2, 4), (3, 4))
        }
        for color in range(5):
            self.assertEqual(map_action(61 + color, view, legal), CanonicalAction("return_token", (color,)))

    def test_ahin_cannot_return_gold_when_canonical_bundle_requires_it(self):
        view = BoardView(tuple(range(12)), (), (), (), (0, 0, 0, 0, 0, 12))
        with self.assertRaisesRegex(AdapterError, "cannot return gold"):
            complete_return(view, (), {CanonicalAction("return", (0, 0, 0, 0, 0, 2))})

    def test_ahin_payment_matches_automatic_colored_then_gold_policy(self):
        action = canonical_payment_for_ahin((2, 2, 0, 0, 1), (0, 1, 0, 0, 0), (1, 1, 0, 0, 0, 2))
        self.assertEqual(action, CanonicalAction("pay", (1, 1, 0, 0, 0)))

    def test_pass_has_no_canonical_mapping(self):
        view = BoardView(tuple(range(12)), (), (), (), (0, 0, 0, 0, 0, 0))
        with self.assertRaisesRegex(AdapterError, "no canonical Rust action"):
            map_action(60, view, set())


if __name__ == "__main__":
    unittest.main()
