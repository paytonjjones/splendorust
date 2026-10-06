"""Small, offline contract tests for the Sprint 48 DAgger relabeler."""
from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.sprint48 import learner_data as ld


class LearnerDataTests(unittest.TestCase):
    def test_candidate_credit_uses_candidate_seat_and_keeps_draws(self):
        record = {"seats": ["alphazero", "champion"], "status": "complete",
                  "rewards": [0.0, 1.0]}
        self.assertEqual(ld.candidate_seat(record), 1)
        self.assertEqual(ld.candidate_credit(record), 1.0)
        record["rewards"] = [0.5, 0.5]
        self.assertEqual(ld.candidate_credit(record), 0.5)
        record["status"] = "decision_limit"
        with self.assertRaises(ValueError):
            ld.candidate_credit(record)

    def test_paired_blocks_reject_missing_rotation_and_different_setup(self):
        pair = [dict(block=4, rotation=i, setup_seed=900, initial_state=[1]) for i in (0, 1)]
        self.assertEqual(ld.paired_blocks(pair, 1)[0][0], 4)
        with self.assertRaises(ValueError):
            ld.paired_blocks(pair[:1], 1)
        pair[1]["setup_seed"] = 901
        with self.assertRaises(ValueError):
            ld.paired_blocks(pair, 1)

    def test_worker_assignment_is_disjoint_and_complete(self):
        assignment = [ld.block_owner(block, 4) for block in range(40)]
        self.assertEqual(assignment, [block % 4 for block in range(40)])
        self.assertEqual(set(assignment), {0, 1, 2, 3})

    def test_setup_id_exclusion_file_supports_comments(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "split-ids.txt"
            path.write_text("# train setups\n12\n13\n\n")
            self.assertEqual(ld.read_setup_ids(path), {12, 13})
            self.assertEqual(ld.read_setup_ids(None), set())

    def test_setup_split_checks_exact_and_native_low32_ids(self):
        ld.check_setup_id_disjoint({17}, {18})
        with self.assertRaises(ValueError):
            ld.check_setup_id_disjoint({17}, {17 + 2**32})
        with self.assertRaises(ValueError):
            ld.check_setup_id_disjoint({17, 17 + 2**32}, set())

    def test_final_external_master_is_not_a_training_source(self):
        record = {"seats": ["champion", "alphazero"], "status": "complete",
                  "rewards": [1.0, 0.0], "native_rewards": [1, -1],
                  "index": 0, "rotation": 0, "block": 0, "setup_seed": 5,
                  "initial_state": [1], "termination": "native_score"}
        second = dict(record, index=1, rotation=1,
                      seats=["alphazero", "champion"], rewards=[0.0, 1.0])
        metadata = {"engine": "alphazero_native", "ruleset": ld.PROFILE,
                    "upstream_revision": ld.PIN,
                    "upstream_checkpoint_sha256": ld.TEACHER_CHECKPOINT_SHA256,
                    "external_config": {"numMCTSSims": 800},
                    "model_sha256": "unused", "master": ld.FINAL_EXTERNAL_MASTER,
                    "games": 2}
        with tempfile.TemporaryDirectory() as temporary:
            descriptor = Path(temporary) / "model.bin"
            descriptor.write_bytes(b"descriptor")
            metadata["model_sha256"] = ld.sha(descriptor)
            with self.assertRaisesRegex(ValueError, "final external master"):
                ld.validate_schedule(metadata, [record, second], descriptor)

    def test_observation_context_masks_private_reservation_identity(self):
        observation = {"viewer": 0, "players": [
            {"reserved": [], "reserved_count": 0},
            {"reserved_count": 2, "reserved": [
                {"public": False, "card": 255, "tier": 0},
                {"public": True, "card": 37, "tier": 2},
            ]},
        ]}
        context = ld.observation_context(observation)
        np.testing.assert_array_equal(context, np.asarray([1, 0, 0, 1 / 3, 1, 0, 1 / 3], dtype="<f4"))
        observation["players"][1]["reserved"][0]["card"] = 31
        with self.assertRaises(ValueError):
            ld.observation_context(observation)

    def test_teacher_query_is_fresh_root_argmax_and_uses_selected_q(self):
        class Tree:
            nodes_data = {b"root": [None, None, None, None, np.asarray([0.25, -0.5]),
                                     np.asarray([2, 4]) ]}

            def getActionProb(self, canonical, temp, force_full_search):
                self.query = (temp, force_full_search)
                return np.asarray([0.1, 0.9]), None, True

        class Game:
            @staticmethod
            def getCanonicalForm(state, actor):
                return np.asarray([actor, 7], dtype=np.int8)

            @staticmethod
            def stringRepresentation(canonical):
                return b"root"

        class Fake:
            def __init__(self):
                self.tree = Tree()
                self.game = Game()
                self.torch = type("Torch", (), {"no_grad": staticmethod(contextlib.nullcontext)})
                self.reset = None

            def reset_policy(self, seed):
                self.reset = seed

        teacher = Fake()
        action, value = ld.teacher_target(teacher, np.asarray([0]), 1, 8, 1234, [0, 1])
        self.assertEqual(teacher.reset, 1234)
        self.assertEqual(teacher.tree.query, (0.0, True))
        self.assertEqual(action, 1)
        self.assertEqual(value, 0.25)


if __name__ == "__main__":
    unittest.main()
