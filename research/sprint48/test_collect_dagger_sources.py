import sys
import tempfile
import unittest
from pathlib import Path

from collect_dagger_sources import run_logged
from learner_data import check_setup_id_disjoint


class SourceCollectorTests(unittest.TestCase):
    def test_finite_source_schedule_settings_are_fixed(self):
        from collect_dagger_sources import (
            DEV_GAMES,
            DEV_MASTER,
            GUMBEL_MAX_CONSIDERED,
            ITERATIONS,
            TRAIN_GAMES,
            TRAIN_MASTER,
            WORKERS,
            FROZEN_BINARY_SHA256,
            FROZEN_COMPILED_SOURCE_SHA256,
            PARENT_SHA256,
        )

        self.assertEqual((TRAIN_MASTER, DEV_MASTER), (17710000000, 17720000000))
        self.assertEqual((TRAIN_GAMES, DEV_GAMES), (1024, 256))
        self.assertEqual((TRAIN_GAMES // 2, DEV_GAMES // 2), (512, 128))
        self.assertEqual(WORKERS, 64)
        self.assertEqual((ITERATIONS, GUMBEL_MAX_CONSIDERED), (128, 16))
        self.assertEqual(PARENT_SHA256, "44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f")
        self.assertEqual(set(FROZEN_BINARY_SHA256), {
            "native_policy_worker", "strength_worker", "transfer_parity"})
        self.assertEqual(len(FROZEN_COMPILED_SOURCE_SHA256), 5)

    def test_fit_uses_preregistered_ten_percent_mixture(self):
        from branch2_train import BATCH, DAGGER_ROWS_PER_UPDATE

        self.assertEqual((BATCH, DAGGER_ROWS_PER_UPDATE), (512, 57))

    def test_run_logged_records_pid_command_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "command.log"
            result = run_logged([sys.executable, "-c", "print('ok')"], log)
            self.assertEqual(result["exit_code"], 0)
            self.assertIsInstance(result["pid"], int)
            self.assertEqual(result["command"][0], sys.executable)
            self.assertEqual(len(result["log_sha256"]), 64)
            self.assertIn("ok", log.read_text())

    def test_native_low32_collision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "low32"):
            check_setup_id_disjoint([7], {2**32 + 7})


if __name__ == "__main__":
    unittest.main()
