"""Optional external audit tests: SPLENDOR_REFERENCE=/path/to/checkout python3 -m unittest discover -s scripts -p test_reference.py."""
import copy
import collections
import json
import os
import pathlib
import subprocess
import unittest

from check_reference import Comparison, ROOT, validate_sampling


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
        noble_branches = {3: 0, 4: 0}
        terminal_counts = {2: 0, 3: 0, 4: 0}
        for case in lines[1:]:
            validate_sampling(lines[0], case)
            before, after = case["before"], case["after"]
            boundary = (after["terminal"] or any(a[0] == 7 for a in case["actions"])
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

    def test_branch_successor_corruption_is_detected(self):
        case = copy.deepcopy(self.cases[0])
        case["choices"][0]["after"]["players"][0]["score"] += 1
        with self.assertRaisesRegex(ValueError, "successor mismatch"):
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
        with self.assertRaisesRegex(ValueError, "successor mismatch"):
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
