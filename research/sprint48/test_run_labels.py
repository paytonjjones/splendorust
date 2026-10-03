"""Offline checks for exact source-block assignment."""
import unittest

from research.sprint48.run_labels import assign_blocks, source_blocks, validate_split_master


class LabelSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.blocks = []
        for block in range(64):
            pair = [dict(setup_seed=1000 + block, status="complete")]
            self.blocks.append((block, pair))

    def test_eight_shards_cover_every_unskipped_block_once(self):
        skipped = {1000}
        assignment = assign_blocks(self.blocks, 8, skipped)
        flattened = [block for worker_blocks in assignment.values() for block in worker_blocks]
        self.assertEqual(sorted(flattened), list(range(1, 64)))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(len(assignment[0]), 7)
        self.assertTrue(all(len(assignment[i]) == 8 for i in range(1, 8)))

    def test_source_blocks_rejects_incomplete_games(self):
        records = []
        for block in range(2):
            for rotation in (0, 1):
                records.append(dict(block=block, rotation=rotation, setup_seed=block,
                                    initial_state=[block], status="complete"))
        self.assertEqual(len(source_blocks({}, records, 2)), 2)
        records[2]["status"] = "decision_limit"
        with self.assertRaises(ValueError):
            source_blocks({}, records, 2)

    def test_dev_source_must_use_reserved_development_master(self):
        base = 17720000000
        validate_split_master("dev", base)
        validate_split_master("train", 17700000000)
        with self.assertRaisesRegex(ValueError, "new-development"):
            validate_split_master("dev", 17700000000)


if __name__ == "__main__":
    unittest.main()
