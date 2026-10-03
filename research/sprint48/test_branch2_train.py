import sys
import unittest

import numpy as np
import torch

from branch2_train import DaggerSampler, weighted_mix_loss
from flywheel_model import DTYPE


class BranchTwoMixTests(unittest.TestCase):
    def test_fixed_loss_ratio_for_full_and_partial_base_batches(self):
        for base_count in (1, 512):
            per_row = torch.tensor([2.0] * base_count + [8.0] * 57)
            loss, base_loss, dagger_loss = weighted_mix_loss(per_row, base_count)
            self.assertEqual(base_loss.item(), 2.0)
            self.assertEqual(dagger_loss.item(), 8.0)
            self.assertAlmostEqual(loss.item(), 0.90 * 2.0 + 0.10 * 8.0, places=6)

    def test_dagger_sampler_keeps_sampled_row_and_input_aligned(self):
        rows_a = np.zeros(2, dtype=DTYPE)
        rows_b = np.zeros(3, dtype=DTYPE)
        rows_a["setup"] = [11, 12]
        rows_b["setup"] = [21, 22, 23]
        inputs_a = np.zeros((2, 525), dtype="<f4")
        inputs_b = np.zeros((3, 525), dtype="<f4")
        inputs_a[:, 0] = rows_a["setup"]
        inputs_b[:, 0] = rows_b["setup"]
        sampler = DaggerSampler([(rows_a, inputs_a, True), (rows_b, inputs_b, True)])
        sampled, packed = sampler.sample(57, np.random.default_rng(123))
        self.assertEqual(len(sampled), 57)
        self.assertEqual(packed.shape, (57, 525))
        np.testing.assert_array_equal(sampled["setup"].astype("<f4"), packed[:, 0])
        self.assertTrue(set(map(int, sampled["setup"])) <= {11, 12, 21, 22, 23})


if __name__ == "__main__":
    unittest.main()
