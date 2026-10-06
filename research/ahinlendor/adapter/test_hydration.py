from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from hydration import build_load_state_payload
from adapter import AdapterError

ROOT = Path(__file__).resolve().parents[3]
AHIN = ROOT / "local/strength/external/ahinlendor"
EXTENSION = next(AHIN.glob("splendor_native*.so"), None)


def observation(*, hidden_reservation: bool = False) -> dict:
    market = list(range(4)) + list(range(40, 44)) + list(range(70, 74))
    return {
        "schema": "ahin-referee-observation-v1",
        "turn_id": 0,
        "decision_id": 0,
        "pending_card_id": None,
        "viewer": 0,
        "current": 0,
        "count": 2,
        "phase": "main",
        "final_round": False,
        "turns": 0,
        "bank": [4, 4, 4, 4, 4, 5],
        "market": market,
        "remaining": [35 if hidden_reservation else 36, 26, 16],
        "nobles": [0, 1, 2],
        "players": [
            {"tokens": [0, 0, 0, 0, 0, 0], "bonuses": [0] * 5, "score": 0,
             "owned_card_ids": [], "nobles": [], "reserved": []},
            {"tokens": [0, 0, 0, 0, 0, 0], "bonuses": [0] * 5, "score": 0,
             "owned_card_ids": [], "nobles": [],
             "reserved": ([{"card_id": None, "tier": 0, "public": False}]
                         if hidden_reservation else [])},
        ],
        "legal_actions": [{"kind": "take", "values": [1, 1, 1, 0, 0]}],
        "terminal": False,
    }


def native_module():
    if EXTENSION is None:
        raise unittest.SkipTest("run research/ahinlendor/external/build.py to build local CPU extension")
    sys.path.insert(0, str(AHIN))
    spec = importlib.util.spec_from_file_location("splendor_native", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HydrationTests(unittest.TestCase):
    def test_samples_hidden_identity_and_deck_only_from_unseen_public_pool(self):
        obs = observation(hidden_reservation=True)
        payload = build_load_state_payload(obs, sample_seed=11)
        reserved = payload["players"][1]["reserved"][0]
        self.assertFalse(reserved["is_public"])
        self.assertIn(reserved["card_id"], range(1, 41))
        self.assertEqual(len(payload["deck_card_ids_by_tier"][0]), 35)
        self.assertNotIn(reserved["card_id"], payload["deck_card_ids_by_tier"][0])
        self.assertEqual(len(set(payload["faceup_card_ids"][0] + payload["deck_card_ids_by_tier"][0]
                                 + [reserved["card_id"]])), 40)

    def test_public_projection_is_identical_across_hidden_samples(self):
        obs = observation(hidden_reservation=True)
        first = build_load_state_payload(obs, sample_seed=11)
        second = build_load_state_payload(obs, sample_seed=12)
        for key in ("current_player", "move_number", "faceup_card_ids", "available_noble_ids", "bank", "phase_flags"):
            self.assertEqual(first[key], second[key])
        self.assertNotEqual(first["players"][1]["reserved"], second["players"][1]["reserved"])
        self.assertNotEqual(first["deck_card_ids_by_tier"], second["deck_card_ids_by_tier"])

    def test_rejects_omniscient_export_fields_and_known_blind_identity(self):
        obs = observation(hidden_reservation=True)
        with self.assertRaisesRegex(AdapterError, "unexpected observation fields"):
            build_load_state_payload({**obs, "deck_card_ids_by_tier": [[], [], []]}, sample_seed=1)
        obs["players"][1]["reserved"][0]["card_id"] = 9
        with self.assertRaisesRegex(AdapterError, "blind reservation identity must be hidden"):
            build_load_state_payload(obs, sample_seed=1)

    def test_rejects_payment_terminal_and_nonacting_viewer(self):
        for phase in ("payment", "terminal"):
            obs = observation()
            obs["phase"] = phase
            if phase == "payment":
                obs["pending_card_id"] = 0
            with self.assertRaisesRegex(AdapterError, "cannot start"):
                build_load_state_payload(obs, sample_seed=1)
        obs = observation()
        obs["viewer"] = 1
        with self.assertRaisesRegex(AdapterError, "acting viewer"):
            build_load_state_payload(obs, sample_seed=1)

    def test_rejects_bad_market_container_as_adapter_error(self):
        obs = observation()
        obs["market"] = None
        with self.assertRaisesRegex(AdapterError, "market must contain"):
            build_load_state_payload(obs, sample_seed=1)

    def test_real_extension_loads_only_sampled_state_and_builds_legal_mask(self):
        module = native_module()
        payload = build_load_state_payload(observation(hidden_reservation=True), sample_seed=91)
        env = module.NativeEnv()
        state = env.load_state(payload)
        self.assertEqual(state.current_player_id, 0)
        self.assertFalse(state.is_terminal)
        self.assertGreater(int(state.mask.sum()), 0)
        exported = env.export_state()
        self.assertEqual(exported["faceup_card_ids"], payload["faceup_card_ids"])
        self.assertEqual(exported["players"][1]["reserved"][0]["card_id"],
                         payload["players"][1]["reserved"][0]["card_id"])
        self.assertNotIn(exported["players"][1]["reserved"][0]["card_id"],
                         exported["deck_card_ids_by_tier"][0])

    def test_real_extension_loads_depleted_market_and_zero_deck_tier(self):
        module = native_module()
        obs = observation()
        cards = module.list_standard_cards()
        tier_one = [card for card in cards if card["tier"] == 1]
        obs["market"] = [None] * 4 + obs["market"][4:]
        obs["remaining"][0] = 0
        for player_index, owned in ((0, tier_one[:20]), (1, tier_one[20:])):
            colors = {name: 0 for name in ("white", "blue", "green", "red", "black")}
            points = 0
            for card in owned:
                colors[card["bonus_color"]] += 1
                points += card["points"]
            obs["players"][player_index]["owned_card_ids"] = [card["id"] - 1 for card in owned]
            obs["players"][player_index]["bonuses"] = [colors[name] for name in colors]
            obs["players"][player_index]["score"] = points
        payload = build_load_state_payload(obs, sample_seed=3)
        self.assertEqual(payload["faceup_card_ids"][0], [0, 0, 0, 0])
        self.assertEqual(payload["deck_card_ids_by_tier"][0], [])
        state = module.NativeEnv().load_state(payload)
        self.assertGreater(int(state.mask.sum()), 0)

    def test_final_round_boundary_matches_pinned_two_player_engine(self):
        module = native_module()
        obs = observation()
        cards = module.list_standard_cards()
        five_point = [card for card in cards
                      if card["tier"] == 3 and card["points"] == 5
                      and card["id"] - 1 not in obs["market"]]
        self.assertGreaterEqual(len(five_point), 3)
        selected = five_point[:3]
        colors = {name: 0 for name in ("white", "blue", "green", "red", "black")}
        for card in selected:
            colors[card["bonus_color"]] += 1
        obs["players"][0]["owned_card_ids"] = [card["id"] - 1 for card in selected]
        obs["players"][0]["bonuses"] = [colors[name] for name in colors]
        obs["players"][0]["score"] = 15
        obs["remaining"][2] = 13
        obs["final_round"] = True
        obs["turns"] = 1
        obs["turn_id"] = 1
        obs["viewer"] = obs["current"] = 1
        payload = build_load_state_payload(obs, sample_seed=9)
        after_triggering_player = module.NativeEnv().load_state(payload)
        self.assertFalse(after_triggering_player.is_terminal)
        self.assertEqual(payload["metadata"]["final_round"], True)

        # The wrapped move back to player 0 ends the game under Ahin's native
        # rule. This state is for engine parity only; the referee emits no
        # search prompt after the terminal boundary.
        payload["current_player"] = 0
        terminal = module.NativeEnv().load_state(payload)
        self.assertTrue(terminal.is_terminal)


if __name__ == "__main__":
    unittest.main()
