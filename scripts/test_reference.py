"""Optional external audit tests: SPLENDOR_REFERENCE=/path/to/checkout python3 -m unittest discover -s scripts -p test_reference.py."""
import copy
import json
import os
import pathlib
import subprocess
import unittest

from check_reference import Comparison, ROOT


@unittest.skipUnless(os.environ.get("SPLENDOR_REFERENCE"), "set SPLENDOR_REFERENCE to the pinned checkout")
class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comparison = Comparison(pathlib.Path(os.environ["SPLENDOR_REFERENCE"]))
        run = subprocess.run(
            ["cargo", "run", "--quiet", "--release", "--locked", "--example", "parity_export", "--", "2", "92000000", "10"],
            cwd=ROOT, check=True, capture_output=True, text=True)
        cls.cases = [json.loads(line) for line in run.stdout.splitlines()[1:]]

    def test_shared_transitions_and_explicit_exclusions(self):
        results = {self.comparison.compare(case) for case in self.cases}
        self.assertEqual(results, {"matched", "blind_reservation", "return_collected_color", "optional_gold_payment", "no_legal_action"})

    def test_shared_action_sets(self):
        checked = 0
        for case in self.cases:
            if case.get("choices") is not None:
                self.comparison.compare_choices(case)
                checked += 1
        self.assertGreater(checked, 0)

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
