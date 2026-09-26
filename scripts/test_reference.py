"""Optional external audit tests: SPLENDOR_REFERENCE=/path/to/checkout python3 -m unittest discover -s scripts -p test_reference.py."""
import copy
import collections
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import unittest
from unittest import mock

from check_reference import Comparison, ROOT, SharedChains, WorkloadSequence, boundary_coverage, validate_sampling


class WorkloadSequenceTests(unittest.TestCase):
    @staticmethod
    def cases():
        result = []
        for count in (2, 3, 4):
            before = {"players": [{}] * count, "turns": 0, "terminal": False}
            middle = {**before, "turns": 1}
            end = {**before, "turns": 2, "terminal": True}
            for old, new in ((before, middle), (middle, end)):
                result.append({"seed": count * 1_000_000, "policy": "strong",
                               "before": old, "after": new})
        return result

    def check(self, cases):
        sequence = WorkloadSequence({"games_per_player_count": 1, "seed": 0})
        for case in cases:
            sequence.add(case)
        return sequence.finish()

    def test_full_sequence_and_corruption(self):
        cases = self.cases()
        self.assertEqual(self.check(cases)["games"], 3)
        for bad in (cases[1:], cases[:-1], cases[:1] + cases, cases + cases[-2:], cases[:2] + cases[4:]):
            with self.assertRaises(ValueError):
                self.check(bad)
        for field, value in (("seed", 99), ("policy", "random")):
            bad = copy.deepcopy(cases)
            bad[2][field] = value
            with self.assertRaises(ValueError):
                self.check(bad)
        bad = copy.deepcopy(cases)
        bad[1]["before"] = copy.deepcopy(bad[1]["before"])
        bad[1]["before"]["players"][0]["injected"] = True
        with self.assertRaisesRegex(ValueError, "discontinuity"):
            self.check(bad)

    def test_blocked_and_capped_sequences(self):
        cases = self.cases()
        for case in cases[1::2]:
            case["after"] = case["before"]
            case["status"] = "no_legal_action"
        self.assertEqual(self.check(cases)["games"], 3)
        capped = []
        for count in (2, 3, 4):
            for turn in range(1000):
                before = {"players": [{}] * count, "turns": turn, "terminal": False}
                capped.append({"seed": count * 1_000_000, "policy": "strong",
                               "before": before, "after": {**before, "turns": turn + 1}})
        self.assertEqual(self.check(capped)["games"], 3)
        self.assertFalse(WorkloadSequence({"depletion_tier": 1}).finish()["checked"])
        for metadata in ({}, {"depletion_tier": True}, {"depletion_tier": 3},
                         {"games_per_player_count": 1, "seed": 0, "depletion_tier": 1},
                         {"games_per_player_count": True, "seed": 0}):
            with self.assertRaises(ValueError):
                WorkloadSequence(metadata)


class CoverageTests(unittest.TestCase):
    def test_reservation_slots_keep_visibility_when_compacted(self):
        reserved = [{"card": 0, "public": False}, {"card": 1, "public": True},
                    {"card": 2, "public": False}]
        before = {"current": 0, "players": [{"reserved": reserved}], "market": [3]}
        for slot in range(3):
            after = {"players": [{"reserved": reserved[:slot] + reserved[slot+1:]}]}
            Comparison.check_reservation_bookkeeping(before, after, [[4, slot]])
            bad = copy.deepcopy(after)
            bad["players"][0]["reserved"][0]["public"] ^= True
            with self.assertRaisesRegex(ValueError, "visibility"):
                Comparison.check_reservation_bookkeeping(before, bad, [[4, slot]])
        empty = {"current": 0, "players": [{"reserved": []}], "market": [3]}
        for tag, public in ((1, True), (2, False)):
            after = {"players": [{"reserved": [{"card": 3, "public": public}]}]}
            Comparison.check_reservation_bookkeeping(empty, after, [[tag, 0]])
            after["players"][0]["reserved"][0]["public"] = not public
            with self.assertRaises(ValueError):
                Comparison.check_reservation_bookkeeping(empty, after, [[tag, 0]])

    def test_automatic_noble_sampling_is_explicit_and_required(self):
        case = {"before": {"turns": 1, "final_round": False, "nobles": [0, 1]},
                "after": {"terminal": False, "final_round": False, "nobles": [1]},
                "actions": [[0, 1, 1, 1, 0, 0, 0]], "choices": None}
        legacy = {"boundary_choices": True, "choice_interval": 0}
        validate_sampling(legacy, case)
        current = {**legacy, "noble_acquisition_choices": True}
        with self.assertRaisesRegex(ValueError, "missing required choice sample"):
            validate_sampling(current, case)
        validate_sampling(current, {**case, "choices": []})
        with self.assertRaisesRegex(ValueError, "invalid noble acquisition sampling flag"):
            validate_sampling({**current, "noble_acquisition_choices": 1}, case)
        with self.assertRaisesRegex(ValueError, "requires boundary sampling"):
            validate_sampling({**current, "boundary_choices": False}, case)

    def test_tier_draw_and_empty_deck_boundaries_are_separate(self):
        before = {"current": 0, "remaining": [0, 1, 0], "bank": [0]*6,
                  "players": [{"tokens": [0]*6, "nobles": []}]}
        after = copy.deepcopy(before)
        after["remaining"][1] = 0
        counts = boundary_coverage(before, after, [[1, 7, 0, 0, 0, 0, 0]])
        self.assertEqual(counts["tier_2_final_draw"], 1)
        self.assertEqual(counts["tier_2_empty_deck_reserve"], 0)
        self.assertEqual(counts["reserve_without_gold"], 1)
        counts = boundary_coverage(before, after, [[3, 11, 0, 0, 0, 0, 0], [5, 0, 0, 0, 0, 0, 0]])
        self.assertEqual(counts["tier_3_empty_deck_purchase"], 1)
        self.assertEqual(counts["tier_3_final_draw"], 0)
        self.assertEqual(counts["free_purchase"], 1)

    def test_gold_payment_is_not_free_and_return_gold_is_separate(self):
        before = {"current": 0, "remaining": [2, 2, 2], "bank": [0]*6,
                  "players": [{"tokens": [0, 0, 0, 0, 0, 1], "nobles": [], "reserved": [{"card": 0, "public": False}]}]}
        after = copy.deepcopy(before)
        after["players"][0]["tokens"][5] = 0
        counts = boundary_coverage(before, after, [[4, 0, 0, 0, 0, 0, 0], [5, 0, 0, 0, 0, 0, 0]])
        self.assertEqual(counts["required_gold_payment"], 1)
        self.assertEqual(counts["free_purchase"], 0)
        self.assertEqual(counts["return_gold"], 0)
        after["players"][0]["nobles"] = [0]
        counts = boundary_coverage(before, after, [[0, 1, 1, 1, 0, 0, 0], [6, 0, 0, 0, 0, 0, 1]])
        self.assertEqual(counts["return_gold"], 1)
        self.assertEqual(counts["noble_after_take"], 1)
        self.assertEqual(counts["noble_after_reserve"], 0)


@unittest.skipUnless(os.environ.get("SPLENDOR_REFERENCE"), "set SPLENDOR_REFERENCE to the pinned checkout")
class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comparison = Comparison(pathlib.Path(os.environ["SPLENDOR_REFERENCE"]))
        run = subprocess.run(
            ["cargo", "run", "--quiet", "--release", "--locked", "--example", "parity_export", "--", "2", "92000000", "10", "true"],
            cwd=ROOT, check=True, capture_output=True, text=True)
        cls.metadata = json.loads(run.stdout.splitlines()[0])
        cls.cases = [json.loads(line) for line in run.stdout.splitlines()[1:]]

    def test_shared_chains_retain_state_and_reset_only_at_gaps(self):
        results = [self.comparison.compare(case) for case in self.cases]
        chains = SharedChains(self.comparison)
        with mock.patch.object(self.comparison, "hydrate", wraps=self.comparison.hydrate) as hydrate:
            for case, result in zip(self.cases, results):
                chains.add(case, result)
            summary = chains.finish()
            self.assertEqual(hydrate.call_count, summary["segments"])
        self.assertEqual(summary["turns"], results.count("matched"))
        self.assertGreater(summary["max_segment_turns"], 1)
        self.assertTrue(summary["breaks"])

    def test_shared_chains_detect_retained_state_corruption(self):
        first, second = self.cases[:2]
        self.assertEqual(self.comparison.compare(first), "matched")
        self.assertEqual(self.comparison.compare(second), "matched")
        chains = SharedChains(self.comparison)
        chains.add(first, "matched")
        chains.rule.current_game_state.board.gems["white"] += 1
        with self.assertRaisesRegex(ValueError, "retained reference state differs"):
            chains.add(second, "matched")

    def test_retained_deck_partition_rejects_hidden_corruption(self):
        first, second = self.cases[:2]
        for corruption in ("duplicate", "wrong_tier"):
            with self.subTest(corruption=corruption):
                chains = SharedChains(self.comparison)
                chains.add(first, "matched")
                decks = chains.rule.current_game_state.board.decks
                if corruption == "duplicate":
                    decks[0][0] = decks[0][1]
                else:
                    decks[0][0], decks[1][0] = decks[1][0], decks[0][0]
                with self.assertRaisesRegex(ValueError, "reference deck partition"):
                    chains.add(second, "matched")
        chains = SharedChains(self.comparison)
        chains.add(first, "matched")
        for deck in chains.rule.current_game_state.board.decks:
            deck.reverse()
        chains.add(second, "matched")
        self.assertEqual(chains.finish()["turns"], 2)

    def test_exclusions_do_not_hide_token_corruption(self):
        examples = {}
        for case in self.cases:
            reason = self.comparison.compare(case)
            if reason in ('blind_reservation', 'optional_gold_payment', 'return_collected_color'):
                examples.setdefault(reason, case)
        self.assertEqual(len(examples), 3)
        examples['seven_card_limit'] = json.loads(
            (ROOT / 'scripts/fixtures/reference-seven-card-successor.json').read_text())
        for reason, case in examples.items():
            self.assertEqual(self.comparison.compare(case), reason)
            for balanced in (False, True):
                bad = copy.deepcopy(case)
                if balanced:
                    donor, color = next((i, c) for i, p in enumerate(bad['after']['players'])
                                        for c, n in enumerate(p['tokens']) if n)
                    bad['after']['bank'][color] += 1
                    bad['after']['players'][donor]['tokens'][color] -= 1
                else:
                    bad['after']['bank'][0] += 1
                with self.assertRaisesRegex(ValueError, 'token'):
                    self.comparison.compare(bad)

    def test_excluded_branch_checks_tokens_before_skipping(self):
        case = copy.deepcopy(self.cases[0])
        choice = next(c for c in case['choices'] if c['actions'][0][0] == 2)
        choice['after']['bank'][0] += 1
        with self.assertRaisesRegex(ValueError, 'token'):
            self.comparison.compare_choices(case, check_successors=True)

    def test_excluded_turns_require_exact_turn_progression(self):
        original = self.cases[0]
        branch = next(c for c in original['choices'] if c['actions'][0][0] == 2)
        base = {'before': original['before'], 'after': branch['after'], 'actions': branch['actions']}
        for legacy in (False, True):
            for field, value in [('turns', base['before']['turns']),
                                 ('current', base['before']['current']),
                                 ('final_round', True), ('terminal', True)]:
                bad = copy.deepcopy(base)
                if legacy:
                    bad['before'].pop('winner_mask', None)
                    bad['after'].pop('winner_mask', None)
                bad['after'][field] = value
                with self.assertRaises(ValueError):
                    self.comparison.compare(bad)
        bad = copy.deepcopy(original)
        choice = next(c for c in bad['choices'] if c['actions'][0][0] == 2)
        choice['after']['turns'] = bad['before']['turns']
        with self.assertRaises(ValueError):
            self.comparison.compare_choices(bad, check_successors=True)

    def test_excluded_reservation_cannot_invent_prestige_or_nobles(self):
        original = self.cases[0]
        branch = next(c for c in original['choices'] if c['actions'][0][0] == 2)
        base = {'before': original['before'], 'after': branch['after'], 'actions': branch['actions']}
        actor = base['before']['current']
        for seat in (actor, (actor + 1) % len(base['before']['players'])):
            bad = copy.deepcopy(base)
            bad['after']['players'][seat]['score'] += 1
            with self.assertRaisesRegex(ValueError, 'prestige'):
                self.comparison.compare(bad)
            bad = copy.deepcopy(base)
            noble = bad['after']['nobles'].pop()
            bad['after']['players'][seat]['nobles'].append(noble)
            bad['after']['players'][seat]['score'] += 3
            with self.assertRaisesRegex(ValueError, 'noble'):
                self.comparison.compare(bad)
        bad = copy.deepcopy(original)
        choice = next(c for c in bad['choices'] if c['actions'][0][0] == 2)
        choice['after']['players'][actor]['score'] += 1
        with self.assertRaisesRegex(ValueError, 'prestige'):
            self.comparison.compare_choices(bad, check_successors=True)

    def test_local_noble_accounting_requires_a_visit_and_choice(self):
        case = json.loads((ROOT / 'scripts/fixtures/reference-noble-choice.json').read_text())
        self.comparison.check_prestige_bookkeeping(case['before'], case['after'], case['actions'])
        actor = case['before']['current']
        gained = (set(case['after']['players'][actor]['nobles'])
                  - set(case['before']['players'][actor]['nobles']))
        noble = gained.pop()
        bad = copy.deepcopy(case)
        bad['after']['players'][actor]['nobles'].remove(noble)
        bad['after']['players'][actor]['score'] -= 3
        bad['after']['nobles'].append(noble)
        with self.assertRaisesRegex(ValueError, 'mandatory noble'):
            self.comparison.check_prestige_bookkeeping(bad['before'], bad['after'], bad['actions'])
        with self.assertRaisesRegex(ValueError, 'encoded noble phase'):
            self.comparison.check_prestige_bookkeeping(
                case['before'], case['after'], [a for a in case['actions'] if a[0] != 7])

    def test_blind_reservation_cannot_steal_cards_or_change_deck_accounting(self):
        original = self.cases[0]
        branch = next(c for c in original['choices'] if c['actions'][0][0] == 2)
        actor = original['before']['current']
        tier = branch['actions'][0][1]
        case = {'before': original['before'], 'after': branch['after'], 'actions': branch['actions']}
        self.assertEqual(self.comparison.compare(case), 'blind_reservation')
        used = set(original['before']['market'])
        wrong_tier = next(i for i, card in enumerate(self.comparison.cards)
                          if card.deck_id != tier and i not in used)
        mutations = [
            lambda c: c['after']['players'][actor]['reserved'][-1].update(card=wrong_tier),
            lambda c: c['after']['players'][actor]['reserved'][-1].update(card=c['before']['market'][0]),
            lambda c: c['after']['remaining'].__setitem__(tier, c['before']['remaining'][tier]),
            lambda c: c['after']['market'].__setitem__(0, 255),
            lambda c: c['after']['players'][actor]['bonuses'].__setitem__(0, 1),
            lambda c: c['actions'][0].__setitem__(1, 255),
        ]
        for mutate in mutations:
            bad = copy.deepcopy(case)
            mutate(bad)
            with self.assertRaisesRegex(ValueError, 'blind'):
                self.comparison.compare(bad)
        bad = copy.deepcopy(original)
        choice = next(c for c in bad['choices'] if c['actions'][0][0] == 2)
        choice['after']['players'][actor]['reserved'][-1]['card'] = wrong_tier
        with self.assertRaisesRegex(ValueError, 'blind'):
            self.comparison.compare_choices(bad, check_successors=True)
        alternative = copy.deepcopy(case)
        drawn = alternative['after']['players'][actor]['reserved'][-1]['card']
        replacement = next(i for i, card in enumerate(self.comparison.cards)
                           if card.deck_id == tier and i not in used and i != drawn)
        alternative['after']['players'][actor]['reserved'][-1]['card'] = replacement
        # The export has no original deck order; another unseen same-tier card
        # is consistent with this local contract and must not be called parity.
        self.assertEqual(self.comparison.compare(alternative), 'blind_reservation')

    def test_reservation_visibility_cannot_change_on_an_unrelated_take(self):
        case = json.loads((ROOT / "scripts/fixtures/reference-reservation-visibility.json").read_text())
        self.assertEqual(self.comparison.compare(case), "matched")
        blind = next((i, j) for i, p in enumerate(case["after"]["players"])
                     for j, r in enumerate(p["reserved"]) if not r["public"] and i != case["before"]["current"])
        for value in (True, 0, None):
            bad = copy.deepcopy(case)
            bad["after"]["players"][blind[0]]["reserved"][blind[1]]["public"] = value
            with self.assertRaisesRegex(ValueError, "visibility"):
                self.comparison.compare(bad)

    def test_excluded_blind_branch_still_checks_local_visibility(self):
        case = copy.deepcopy(self.cases[0])
        choice = next(c for c in case["choices"] if c["actions"][0][0] == 2)
        actor = case["before"]["current"]
        choice["after"]["players"][actor]["reserved"][-1]["public"] = True
        with self.assertRaisesRegex(ValueError, "blind reservation append"):
            self.comparison.compare_choices(case, check_successors=True)

    def test_encoded_noble_choice_must_match_successor(self):
        case = json.loads((ROOT / "scripts/fixtures/reference-noble-choice.json").read_text())
        self.assertEqual(self.comparison.compare(case), "matched")
        bad = copy.deepcopy(case)
        noble = next(a for a in bad["actions"] if a[0] == 7)
        noble[1] = (noble[1] + 1) % 10
        with self.assertRaisesRegex(ValueError, "encoded noble choice"):
            self.comparison.compare(bad)
        bad = copy.deepcopy(case)
        bad["actions"].append(copy.deepcopy(bad["actions"][-1]))
        with self.assertRaisesRegex(ValueError, "phase order"):
            self.comparison.compare(bad)
        bad = copy.deepcopy(case)
        bad["actions"].pop()
        with self.assertRaisesRegex(ValueError, "encoded noble phase"):
            self.comparison.compare(bad)
        bad = copy.deepcopy(case)
        bad["actions"][-1][-1] = 1
        with self.assertRaisesRegex(ValueError, "padding"):
            self.comparison.compare(bad)

    def test_winner_checks_keep_reference_tiebreak_defect_explicit(self):
        case = json.loads((ROOT / "scripts/fixtures/reference-winner-tiebreak.json").read_text())
        counts = collections.Counter()
        self.assertEqual(self.comparison.compare(case, counts), "matched")
        self.assertEqual(case["after"]["winner_mask"], 2)
        self.assertEqual(counts["reference_global_fewest_card_defect"], 1)
        self.assertEqual(counts["winner_matches"], 0)
        from unittest.mock import patch
        with patch.object(self.comparison.Rule, "calScore", return_value=1):
            with self.assertRaisesRegex(ValueError, "unclassified reference winner mismatch"):
                self.comparison.compare(case)
        # Copying the reference's incorrect shared result must not pass locally.
        case["after"]["winner_mask"] = 3
        with self.assertRaisesRegex(ValueError, "leader-only fewest-card rule"):
            self.comparison.compare(case)

    def test_unfinished_or_corrupt_winner_data_is_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case["after"]["winner_mask"] = 1
        with self.assertRaisesRegex(ValueError, "unfinished state has a winner"):
            self.comparison.compare(case)
        case = copy.deepcopy(self.cases[0])
        case["after"]["final_round"] = True
        with self.assertRaisesRegex(ValueError, "final-round flag"):
            self.comparison.compare(case)
        case = copy.deepcopy(self.cases[0])
        del case["after"]["winner_mask"]
        with self.assertRaisesRegex(ValueError, "missing exported winner mask"):
            validate_sampling(self.metadata, case)
        case = copy.deepcopy(self.cases[0])
        del case["choices"][0]["after"]["winner_mask"]
        with self.assertRaisesRegex(ValueError, "missing branch winner mask"):
            validate_sampling(self.metadata, case)

    def test_normal_winners_match_and_blocked_games_have_none(self):
        counts = collections.Counter()
        for case in self.cases:
            self.comparison.compare(case, counts)
        self.assertGreater(counts["winner_matches"], 0)
        self.assertGreater(counts["blocked_without_winner"], 0)

    def test_known_reference_seven_card_limit_is_explicit(self):
        case = json.loads((ROOT / "scripts/fixtures/reference-seven-card-limit.json").read_text())
        counts = self.comparison.compare_choices(case)
        self.assertEqual(counts["local_seven_card_limit"], 1)
        self.assertGreater(counts["shared_choices"], 0)

    def test_seven_card_exclusion_keeps_full_successors_at_all_player_counts(self):
        manifest = json.loads((ROOT / 'scripts/fixtures/reference-seven-card-branches.json').read_text())
        raw = gzip.decompress((ROOT / manifest['archive']).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['raw_sha256'])
        wanted = {(r['players'], r['seed'], r['turn']): r for r in manifest['cases']}
        self.assertEqual({key[0] for key in wanted}, {2, 3, 4})
        found = set()
        for line in raw.splitlines()[1:]:
            case = json.loads(line)
            key = (len(case['before']['players']), case['seed'], case['before']['turns'])
            if key not in wanted:
                continue
            self.assertNotIn(key, found)
            found.add(key)
            expected = wanted[key]
            digest = hashlib.sha256(json.dumps(case, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(digest, expected['case_sha256'])
            self.assertEqual(len(case['choices']), expected['choices'])
            counts = self.comparison.compare_choices(case, check_successors=True)
            self.assertEqual(dict(counts), expected['expected_counts'])
            self.assertEqual(counts['local_seven_card_limit'], 1)
            self.assertEqual(counts['shared_choices'], counts['shared_successors'])
            rule = self.comparison.hydrate(case['before'], case['before'])
            index = next(i for i, choice in enumerate(case['choices'])
                         if self.comparison.candidate(case['before'], choice['actions'], choice['noble'], rule)
                         == 'seven_card_limit')
            bad = copy.deepcopy(case)
            bad['choices'][index]['after']['bank'][0] += 1
            with self.assertRaisesRegex(ValueError, 'token'):
                self.comparison.compare_choices(bad, check_successors=True)
            bad = copy.deepcopy(case)
            choice = bad['choices'][index]
            choice['noble'] = (choice['noble'] + 1) % 10
            with self.assertRaisesRegex(ValueError, 'choice noble'):
                self.comparison.compare_choices(bad, check_successors=True)
        self.assertEqual(found, set(wanted))

    def test_shared_transitions_and_explicit_exclusions(self):
        results = {self.comparison.compare(case) for case in self.cases}
        self.assertEqual(results, {"matched", "blind_reservation", "return_collected_color", "optional_gold_payment", "no_legal_action"})

    def test_shared_action_sets(self):
        checked = 0
        for case in self.cases:
            if case.get("choices") is not None:
                counts = self.comparison.compare_choices(case, check_successors=True)
                self.assertEqual(counts["shared_choices"], counts["shared_successors"])
                checked += 1
        self.assertGreater(checked, 0)

    def test_boundary_sampling_checks_multiplayer_noble_branches(self):
        run = subprocess.run(
            ["cargo", "run", "--quiet", "--release", "--locked", "--example", "parity_export", "--",
             "8", "92000000", "0", "true", "true"],
            cwd=ROOT, check=True, capture_output=True, text=True)
        lines = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertTrue(lines[0]["boundary_choices"])
        self.assertTrue(lines[0]["noble_acquisition_choices"])
        noble_branches = {3: 0, 4: 0}
        terminal_counts = {2: 0, 3: 0, 4: 0}
        for case in lines[1:]:
            validate_sampling(lines[0], case)
            before, after = case["before"], case["after"]
            boundary = (after["terminal"] or before["nobles"] != after["nobles"]
                        or (not before["final_round"] and after["final_round"]))
            if boundary:
                self.assertIsNotNone(case["choices"])
                missing = {**case, "choices": None}
                with self.assertRaisesRegex(ValueError, "missing required choice sample"):
                    validate_sampling(lines[0], missing)
                counts = self.comparison.compare_choices(case, check_successors=True)
                players = len(before["players"])
                if players in noble_branches:
                    noble_branches[players] += counts["successors_explicit_noble_choice"]
                terminal_counts[players] += counts["successors_terminal"]
            elif case.get("status") != "no_legal_action":
                self.assertIsNone(case["choices"])
        self.assertTrue(all(n >= 2 for n in noble_branches.values()), noble_branches)
        self.assertTrue(all(n > 0 for n in terminal_counts.values()), terminal_counts)

    def test_automatic_nonpurchase_nobles_have_checked_action_sets(self):
        cases = json.loads((ROOT / "scripts/fixtures/reference-automatic-nobles.json").read_text())
        self.assertEqual({c["actions"][0][0] for c in cases}, {0, 1})
        metadata = {"boundary_choices": True, "noble_acquisition_choices": True,
                    "choice_interval": 0, "choice_successors": True, "winner_checks": True}
        totals = collections.Counter()
        for case in cases:
            self.assertFalse(any(a[0] == 7 for a in case["actions"]))
            self.assertFalse(case["after"]["terminal"])
            self.assertEqual(case["before"]["final_round"], case["after"]["final_round"])
            validate_sampling(metadata, case)
            with self.assertRaisesRegex(ValueError, "missing required choice sample"):
                validate_sampling(metadata, {**case, "choices": None})
            self.assertEqual(self.comparison.compare(case), "matched")
            counts = self.comparison.compare_choices(case, check_successors=True)
            self.assertEqual(counts["shared_choices"], counts["shared_successors"])
            totals.update(counts)
        self.assertGreater(totals["boundary_noble_after_take"], 0)
        self.assertGreater(totals["boundary_noble_after_reserve"], 0)

    def test_high_tier_depletion_histories_check_both_empty_slot_actions(self):
        for tier in (2, 3):
            fixture = ROOT / f"crates/splendor-arena/tests/fixtures/depleted-tier-{tier}-v2.json"
            run = subprocess.run(
                ["cargo", "run", "--quiet", "--release", "--locked", "--example", "parity_export", "--",
                 "--history", str(fixture), str(tier - 1)],
                cwd=ROOT, check=True, capture_output=True, text=True)
            lines = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(lines[0]["depletion_tier"], tier - 1)
            counts = collections.Counter()
            for case in lines[1:]:
                validate_sampling(lines[0], case)
                with self.assertRaisesRegex(ValueError, "missing required choice sample"):
                    validate_sampling(lines[0], {**case, "choices": None})
                self.assertIn(self.comparison.compare(case), ("matched", "return_collected_color"))
                counts.update(self.comparison.compare_choices(case, check_successors=True))
            for event in ("final_draw", "empty_deck_purchase", "empty_deck_reserve"):
                self.assertGreater(counts[f"boundary_tier_{tier}_{event}"], 0)

    def test_branch_successor_corruption_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["choices"][0]["after"]["players"][0]["score"] += 1
        with self.assertRaisesRegex(ValueError, "prestige score"):
            self.comparison.compare_choices(case, check_successors=True)
        case = copy.deepcopy(self.cases[0])
        del case["choices"][0]["after"]
        with self.assertRaisesRegex(ValueError, "missing choice successor"):
            self.comparison.compare_choices(case, check_successors=True)

    def test_missing_regular_sample_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        validate_sampling(self.metadata, case)
        del case["choices"]
        with self.assertRaisesRegex(ValueError, "missing required choice sample"):
            validate_sampling(self.metadata, case)

    def test_missing_choice_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        del case["choices"][0]
        with self.assertRaisesRegex(ValueError, "action-set mismatch"):
            self.comparison.compare_choices(case)

    def test_duplicate_choice_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["choices"].append(copy.deepcopy(case["choices"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate local"):
            self.comparison.compare_choices(case)

    def test_corrupt_score_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["after"]["players"][0]["score"] += 1
        with self.assertRaisesRegex(ValueError, "prestige score"):
            self.comparison.compare(case)

    def test_corrupt_bank_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["after"]["bank"][0] += 1
        with self.assertRaisesRegex(ValueError, "successor mismatch"):
            self.comparison.compare(case)

    def test_corrupt_deck_partition_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["before"]["remaining"][0] -= 1
        with self.assertRaisesRegex(ValueError, "deck partition mismatch"):
            self.comparison.compare(case)


if __name__ == "__main__":
    unittest.main()
