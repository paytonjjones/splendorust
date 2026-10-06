"""Map AhinLendor's 69 actions to SplendoRust's public action schema.

This module does not read or construct a referee GameState. Callers must build
BoardView from the acting player's Observation and the canonical legal actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PINNED_AHINLENDOR_REVISION = "96e6f2daff83147495826c4a2073dc3c9c856cc9"
CARD_IDS_AHINLENDOR = tuple(range(1, 91))  # Rust IDs are zero-based; Ahin IDs are one-based.
# Rust noble ID -> Ahin standard noble ID, by exact requirements signature.
NOBLE_IDS_AHINLENDOR = (9, 8, 10, 6, 7, 5, 4, 2, 3, 1)

TAKE3 = (
    (1, 1, 1, 0, 0), (1, 1, 0, 1, 0), (1, 1, 0, 0, 1),
    (1, 0, 1, 1, 0), (1, 0, 1, 0, 1), (1, 0, 0, 1, 1),
    (0, 1, 1, 1, 0), (0, 1, 1, 0, 1), (0, 1, 0, 1, 1),
    (0, 0, 1, 1, 1),
)
TAKE2_SAME = tuple(tuple(2 if i == color else 0 for i in range(5)) for color in range(5))
TAKE2_DIFFERENT = (
    (1, 1, 0, 0, 0), (1, 0, 1, 0, 0), (1, 0, 0, 1, 0),
    (1, 0, 0, 0, 1), (0, 1, 1, 0, 0), (0, 1, 0, 1, 0),
    (0, 1, 0, 0, 1), (0, 0, 1, 1, 0), (0, 0, 1, 0, 1),
    (0, 0, 0, 1, 1),
)
TAKE1 = tuple(tuple(1 if i == color else 0 for i in range(5)) for color in range(5))


class AdapterError(ValueError):
    pass


def card_id_to_ahin(canonical_id: int) -> int:
    if not 0 <= canonical_id < 90:
        raise AdapterError("canonical card ID outside 0..89")
    return canonical_id + 1


def card_id_from_ahin(ahin_id: int) -> int:
    if not 1 <= ahin_id <= 90:
        raise AdapterError("Ahin card ID outside 1..90")
    return ahin_id - 1


def noble_id_to_ahin(canonical_id: int) -> int:
    if not 0 <= canonical_id < 10:
        raise AdapterError("canonical noble ID outside 0..9")
    return NOBLE_IDS_AHINLENDOR[canonical_id]


AHINLENDOR_NOBLE_TO_CANONICAL = tuple(NOBLE_IDS_AHINLENDOR.index(i) for i in range(1, 11))


@dataclass(frozen=True)
class ReservedSlot:
    card_id: int | None
    tier: int
    public: bool


@dataclass(frozen=True)
class BoardView:
    """Only data present in a player's public/private Observation.

    `market` is tier-major, four slots per tier. `noble_ids` gives the exact
    order used to construct Ahin's three available-noble slots.
    """

    market: tuple[int | None, ...]
    own_reserved: tuple[int, ...]
    opponent_reserved: tuple[ReservedSlot, ...]
    noble_ids: tuple[int, ...]
    own_tokens: tuple[int, int, int, int, int, int]

    def __post_init__(self) -> None:
        if len(self.market) != 12 or len(self.noble_ids) > 3 or len(self.own_reserved) > 3:
            raise AdapterError("invalid market, reserved-card, or noble slot count")
        if len(self.opponent_reserved) > 3 or len(self.own_tokens) != 6:
            raise AdapterError("invalid opponent reservation or token count")
        if any(card is not None and not 0 <= card < 90 for card in self.market):
            raise AdapterError("market card ID outside 0..89")
        if any(not 0 <= card < 90 for card in self.own_reserved):
            raise AdapterError("own reserved card ID outside 0..89")
        for slot in self.opponent_reserved:
            if not 0 <= slot.tier < 3:
                raise AdapterError("opponent reservation tier outside 0..2")
            if slot.card_id is not None and (not slot.public or not 0 <= slot.card_id < 90):
                raise AdapterError("opponent blind reservation identity is not observable")
        if any(not 0 <= noble < 10 for noble in self.noble_ids):
            raise AdapterError("noble ID outside 0..9")
        if any(token < 0 for token in self.own_tokens):
            raise AdapterError("negative token count")


@dataclass(frozen=True)
class CanonicalAction:
    kind: str
    values: tuple[int, ...] = ()


def _require_legal(action: CanonicalAction, legal: Iterable[CanonicalAction]) -> CanonicalAction:
    if action not in legal:
        raise AdapterError(f"Ahin action maps to non-legal canonical action: {action}")
    return action


def map_action(index: int, view: BoardView, legal_actions: Iterable[CanonicalAction]) -> CanonicalAction:
    """Map one Ahin root choice to one canonical intent.

    Ahin's return choice is intentionally mapped to a `return_token` intent.
    The caller collects the remaining sequential returns, then submits one
    canonical `return` action for the complete vector.
    """
    if not 0 <= index < 69:
        raise AdapterError("Ahin action index outside 0..68")
    if index < 12:
        slot = index
        if view.market[slot] is None:
            raise AdapterError("Ahin selected an empty face-up slot")
        return _require_legal(CanonicalAction("buy_visible", (slot,)), legal_actions)
    if index < 15:
        slot = index - 12
        if slot >= len(view.own_reserved):
            raise AdapterError("Ahin selected an empty own-reserved slot")
        return _require_legal(CanonicalAction("buy_reserved", (slot,)), legal_actions)
    if index < 27:
        slot = index - 15
        if view.market[slot] is None:
            raise AdapterError("Ahin selected an empty face-up slot")
        return _require_legal(CanonicalAction("reserve_visible", (slot,)), legal_actions)
    if index < 30:
        tier = index - 27
        return _require_legal(CanonicalAction("reserve_deck", (tier,)), legal_actions)
    if index < 40:
        take = TAKE3[index - 30]
        return _require_legal(CanonicalAction("take", take), legal_actions)
    if index < 45:
        take = TAKE2_SAME[index - 40]
        return _require_legal(CanonicalAction("take", take), legal_actions)
    if index < 55:
        take = TAKE2_DIFFERENT[index - 45]
        return _require_legal(CanonicalAction("take", take), legal_actions)
    if index < 60:
        take = TAKE1[index - 55]
        return _require_legal(CanonicalAction("take", take), legal_actions)
    if index == 60:
        raise AdapterError("Ahin PASS_TURN has no canonical Rust action")
    if index < 66:
        color = index - 61
        if view.own_tokens[color] == 0:
            raise AdapterError("Ahin selected a token color that is not held")
        if not any(a.kind == "return" and len(a.values) == 6 and a.values[color] > 0
                   for a in legal_actions):
            raise AdapterError("Ahin return token is not part of any legal canonical return")
        return CanonicalAction("return_token", (color,))
    slot = index - 66
    if slot >= len(view.noble_ids):
        raise AdapterError("Ahin selected an unavailable noble slot")
    return _require_legal(CanonicalAction("noble", (view.noble_ids[slot],)), legal_actions)


def complete_return(view: BoardView, selected_colors: Iterable[int],
                    legal_actions: Iterable[CanonicalAction]) -> CanonicalAction:
    """Collapse Ahin's sequential returns into Rust's required token vector."""
    colors = tuple(selected_colors)
    need = sum(view.own_tokens) - 10
    if need > sum(view.own_tokens[:5]):
        raise AdapterError("Ahin return action space cannot return gold tokens")
    if need <= 0 or len(colors) != need or any(not 0 <= c < 5 for c in colors):
        raise AdapterError("sequential return count does not match the canonical return phase")
    returned = tuple(colors.count(i) for i in range(6))
    if any(returned[i] > view.own_tokens[i] for i in range(6)):
        raise AdapterError("Ahin return sequence exceeds held tokens")
    return _require_legal(CanonicalAction("return", returned), legal_actions)


def canonical_payment_for_ahin(card_cost: tuple[int, int, int, int, int],
                                bonuses: tuple[int, int, int, int, int],
                                tokens: tuple[int, int, int, int, int, int]) -> CanonicalAction:
    """Mirror Ahin's native automatic payment: colored tokens first, then gold."""
    if len(card_cost) != 5 or len(bonuses) != 5 or len(tokens) != 6:
        raise AdapterError("invalid payment vector width")
    payment = tuple(min(max(0, card_cost[i] - bonuses[i]), tokens[i]) for i in range(5))
    shortfall = sum(max(0, card_cost[i] - bonuses[i] - payment[i]) for i in range(5))
    if shortfall > tokens[5]:
        raise AdapterError("Ahin payment policy cannot afford this card")
    return CanonicalAction("pay", payment)
