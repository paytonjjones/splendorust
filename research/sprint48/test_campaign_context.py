"""CPU-only tests for final-campaign provenance without final seeds or games."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import hashlib
import json
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/sprint48"))
sys.path.insert(0, str(ROOT / "benchmarks/strength/native"))
import run as native_run
spec = importlib.util.spec_from_file_location("sprint48_test_freeze", ROOT / "research/sprint48/freeze.py")
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)
from campaign_context import campaign_metadata
from run_final import execute_schedule, utc_now


class CampaignContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48")
        self.directory = Path(self.temp.name)
        self.paths = {}
        for name in ("checkpoint.pt", "descriptor.bin", "export.json", "policy", "strength", "parity", "service.py"):
            path = self.directory / name
            path.write_bytes((name + "-fixture").encode())
            self.paths[name] = path
        for name in ("policy", "strength", "parity"):
            self.paths[name].chmod(0o755)
        self.source_path = self.directory / "source.py"
        self.source_path.write_text("frozen source\n")
        self.source_relative = str(self.source_path.relative_to(ROOT))
        self.manifest = self.make_manifest()
        self.manifest["freeze_sha256"] = freeze.freeze_sha(self.manifest)
        self.freeze_path = self.directory / "synthetic-freeze.json"
        self.freeze_path.write_text(json.dumps(self.manifest))
        self.started = "2026-10-03T20:00:00Z"
        self.context_path = self.directory / "campaign-context.json"
        self.context_path.write_text(json.dumps({
            "schema": "sprint48-final-campaign-context-v1",
            "freeze_path": str(self.freeze_path), "freeze_sha256": self.manifest["freeze_sha256"],
            "campaign_started_at_utc": self.started,
            "checkpoint_path": str(self.paths["checkpoint.pt"]),
            "checkpoint_sha256": freeze.sha(self.paths["checkpoint.pt"]),
            "export_receipt_path": str(self.paths["export.json"]),
            "export_receipt_sha256": freeze.sha(self.paths["export.json"]),
            "parity_binary_path": str(self.paths["parity"]),
            "parity_binary_sha256": freeze.sha(self.paths["parity"]),
            "service_config": {"backend": "cpu", "batch": 32, "delay_ms": 1,
                "port": 19720, "fast_entities": True,
                "source_sha256": freeze.sha(self.paths["service.py"])},
            "source_sha256": self.manifest["source_sha256"]}))
        self.args = SimpleNamespace(games=1000, campaign_games=1000, offset_block=0,
            master=freeze.MASTER, search="puct",
            iterations=1600, depth=32, world_pool=0, chance_universes=0, dynamic_fpu=False,
            gumbel_max_considered=16, root_only=False)

    def tearDown(self):
        self.temp.cleanup()

    def identity(self, name):
        path = self.paths[name]
        return {"path": str(path), "sha256": freeze.sha(path)}

    def make_manifest(self):
        ids = list(range(500000, 500500))
        service_hash = freeze.sha(self.paths["service.py"])
        return {"schema": "sprint48-final-freeze-v1", "frozen_at_utc": "2026-10-03T19:00:00Z",
            "candidate": {"checkpoint": self.identity("checkpoint.pt"),
                "descriptor": self.identity("descriptor.bin"), "export_receipt": self.identity("export.json"),
                "binaries": {"native_policy_worker": self.identity("policy"),
                    "strength_worker": self.identity("strength"), "transfer_parity": self.identity("parity")}},
            "search": {"algorithm": "puct", "iterations": 1600, "depth": 32, "world_pool": 0,
                "chance_universes": 0, "dynamic_fpu": False,
                "gumbel_max_considered": None, "root_only": False, "cpuct": .4,
                "fpu_reduction": .02965, "uniform_prior": 0., "gumbel_noise": 0.,
                "root_noise": 0., "gumbel_cvisit": None, "gumbel_cscale": None},
            "service": {"backend": "cpu", "batch": 32, "delay_ms": 1, "port": 19720,
                "fast_entities": True, "source": {"path": str(self.paths["service.py"]), "sha256": service_hash}},
            "target": {"source_path": str(self.directory), "revision": freeze.AZ_REVISION,
                "working_tree_clean": True, "checkpoint": {"path": str(self.directory / "upstream.pt"),
                    "sha256": freeze.AZ_CHECKPOINT}, "simulations": 800, "profile": freeze.PROFILE,
                "external_config": freeze.AZ_EXTERNAL_CONFIG},
            "evaluation": {"profile": freeze.PROFILE, "games": 1000, "paired_setup_blocks": 500,
                "master": freeze.MASTER, "adaptive_stopping": False, "sample_size_locked_before_outcomes": True,
                "primary_criterion": {"interval": "two-sided Hoeffding 95% over paired setup blocks",
                    "unknown_game_credit_bounds": [0, 1], "radius": "sqrt(log(40)/(2*paired_setup_blocks))",
                    "candidate_lower_credit_strictly_greater_than": .55}, "max_no_action_fraction": .01,
                "reject_statuses": ["invalid", "decision_limit"], "full_planned_schedule_required": True,
                "caps_sensitivity": {"native_turn_cap_as_unknown": True, "same_paired_blocks": True,
                    "report_hoeffding95_interval": True, "primary_threshold_applies_to_caps_sensitivity": False}},
            "seed_audit": {"setup_ids_low32": ids, "setup_ids_sha256": freeze.hash_value(ids),
                "overlap_count": 0, "no_prior_final_outcomes_found": True,
                "output_root_scanned": str(self.directory), "excluded_ids": 0},
            "source_sha256": {self.source_relative: freeze.sha(self.source_path)}}

    def call(self, args=None):
        selected = copy.copy(args or self.args)
        selected.campaign_context = self.context_path
        return native_run.apply_campaign_metadata({}, selected, self.paths["descriptor.bin"],
            self.paths["policy"], self.paths["strength"], freeze.AZ_EXTERNAL_CONFIG)

    def test_valid_context_emits_frozen_metadata_and_source_hashes(self):
        metadata = self.call()
        self.assertEqual(metadata["freeze_sha256"], self.manifest["freeze_sha256"])
        self.assertEqual(metadata["campaign_started_at_utc"], self.started)
        self.assertEqual(metadata["source_sha256"], self.manifest["source_sha256"])
        self.assertEqual(metadata["checkpoint_sha256"], freeze.sha(self.paths["checkpoint.pt"]))

    def test_rejects_changed_checkpoint_and_search_settings(self):
        original = self.paths["checkpoint.pt"].read_bytes()
        self.paths["checkpoint.pt"].write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "artifact differs"):
            self.call()
        self.paths["checkpoint.pt"].write_bytes(original)
        changed = copy.copy(self.args)
        changed.iterations += 1
        with self.assertRaisesRegex(ValueError, "settings differ"):
            self.call(changed)
        changed = copy.copy(self.args)
        changed.chance_universes = 3
        with self.assertRaisesRegex(ValueError, "settings differ"):
            self.call(changed)
        changed = copy.copy(self.args)
        changed.dynamic_fpu = True
        with self.assertRaisesRegex(ValueError, "settings differ"):
            self.call(changed)

    def test_freeze_requires_bounded_chance_universe_setting(self):
        proposal = {"schema": "sprint48-final-proposal-v1", "candidate": {
            "checkpoint": "candidate.pt", "descriptor": "candidate.bin",
            "export_receipt": "export.json", "policy_binary": "policy",
            "strength_binary": "strength", "parity_binary": "parity"},
            "search": {"algorithm": "puct", "iterations": 128, "depth": 16,
                "world_pool": 3, "chance_universes": 0, "dynamic_fpu": False,
                "gumbel_max_considered": None, "root_only": False},
            "service": {"backend": "cpu", "batch": 32, "delay_ms": 1,
                "port": 19720, "fast_entities": True}, "games": 1000}
        freeze._proposal(proposal)
        proposal["search"]["chance_universes"] = 65
        with self.assertRaisesRegex(freeze.FreezeError, "chance_universes"):
            freeze._proposal(proposal)
        proposal["search"]["chance_universes"] = 0
        proposal["search"]["dynamic_fpu"] = "true"
        with self.assertRaisesRegex(freeze.FreezeError, "dynamic_fpu"):
            freeze._proposal(proposal)

    def test_no_context_preserves_unfrozen_native_metadata_path(self):
        args = SimpleNamespace(campaign_context=None)
        self.assertEqual(native_run.apply_campaign_metadata({"legacy": True}, args,
            None, None, None, None), {"legacy": True})

    def test_old_worker_handshake_accepts_only_default_chance_setting(self):
        expected = {"iterations": 128, "depth": 16, "world_pool": 3,
            "gumbel_max_considered": 16, "chance_universes": 0, "dynamic_fpu": False,
            "search": "puct", "root_only": False}
        accepted = {key: value for key, value in expected.items()
            if key not in ("chance_universes", "dynamic_fpu")}
        native_run.validate_accepted_settings(expected, accepted)
        nondefault = expected | {"chance_universes": 3}
        with self.assertRaisesRegex(RuntimeError, "settings differ"):
            native_run.validate_accepted_settings(nondefault, accepted)
        nondefault = expected | {"dynamic_fpu": True}
        with self.assertRaisesRegex(RuntimeError, "settings differ"):
            native_run.validate_accepted_settings(nondefault, accepted)

    def test_native_runner_main_uses_no_context_compatibility_path(self):
        import numpy as np
        output = self.directory / "legacy-no-context.jsonl"
        model = self.directory / "legacy-model.bin"
        model.write_bytes(b"synthetic descriptor")
        policy, strength = self.paths["policy"], self.paths["strength"]

        class FakeRPC:
            def __init__(self, command):
                self.command = command
            def call(self, **payload):
                return {"settings": {"iterations": payload["iterations"], "depth": payload["depth"],
                    "world_pool": payload["world_pool"], "chance_universes": payload["chance_universes"],
                    "dynamic_fpu": payload["dynamic_fpu"],
                    "gumbel_max_considered": payload["gumbel_max_considered"],
                    "search": payload["search"], "root_only": payload["root_only"]}}
            def close(self):
                pass

        class FakeUpstream:
            def __init__(self, network, strength_binary):
                self.strength_binary = Path(strength_binary)
                self.strength_binary_sha256 = native_run.sha(self.strength_binary)
                self.config = freeze.AZ_EXTERNAL_CONFIG
                self.data = {"source_id": "test-only", "engine": "test-only"}
                self.np = np
                self.game = SimpleNamespace(getScore=lambda state, seat: 0)
            def setup(self, seed):
                return np.zeros((1, 7), dtype=np.int8)
            def rewards(self, state, seat):
                return [1, 0]
            def reset_policy(self, seed):
                pass

        class FakeTracker:
            def __init__(self, upstream, state):
                pass

        argv = ["run.py", "--games", "2", "--master", "12345", "--iterations", "128",
            "--model", str(model), "--policy-binary", str(policy), "--strength-binary", str(strength),
            "--output", str(output)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(native_run, "Upstream", FakeUpstream), \
                mock.patch.object(native_run, "RPC", FakeRPC), mock.patch.object(native_run, "Tracker", FakeTracker):
            native_run.main()
        metadata = json.loads(output.read_text().splitlines()[0])
        self.assertEqual(metadata["games"], 2)
        self.assertNotIn("freeze_sha256", metadata)
        self.assertNotIn("campaign_started_at_utc", metadata)

    def test_native_runner_main_binds_shard_to_campaign_total_without_final_draws(self):
        import numpy as np
        output = self.directory / "context-shard.jsonl"

        class FakeRPC:
            def __init__(self, command):
                self.command = command
            def call(self, **payload):
                return {"settings": {key: payload[key] for key in (
                    "iterations", "depth", "world_pool", "chance_universes",
                    "dynamic_fpu", "gumbel_max_considered", "search", "root_only")}}
            def close(self):
                pass

        class FakeUpstream:
            def __init__(self, network, strength_binary):
                self.strength_binary = Path(strength_binary)
                self.strength_binary_sha256 = native_run.sha(self.strength_binary)
                self.config = freeze.AZ_EXTERNAL_CONFIG
                self.data = {"source_id": "test-only", "engine": "test-only"}
                self.np = np
                self.game = SimpleNamespace(getScore=lambda state, seat: 0)
            def setup(self, seed):
                self.received_setup_seed = seed
                return np.zeros((1, 7), dtype=np.int8)
            def rewards(self, state, seat):
                return [1, 0]
            def reset_policy(self, seed):
                pass

        class FakeTracker:
            def __init__(self, upstream, state):
                pass

        argv = ["run.py", "--games", "2", "--campaign-games", "1000",
            "--master", str(freeze.MASTER), "--offset-block", "17", "--iterations", "1600",
            "--depth", "32", "--world-pool", "0", "--chance-universes", "0",
            "--model", str(self.paths["descriptor.bin"]),
            "--policy-binary", str(self.paths["policy"]), "--strength-binary", str(self.paths["strength"]),
            "--campaign-context", str(self.context_path), "--output", str(output)]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(native_run, "Upstream", FakeUpstream), \
                mock.patch.object(native_run, "RPC", FakeRPC), \
                mock.patch.object(native_run, "Tracker", FakeTracker), \
                mock.patch.object(native_run, "stream", side_effect=lambda *_: 42):
            native_run.main()
        header, *rows = map(json.loads, output.read_text().splitlines())
        self.assertEqual(header["games"], 2)
        self.assertEqual(header["campaign_games"], 1000)
        self.assertEqual([row["index"] for row in rows], [34, 35])
        self.assertEqual({row["setup_seed"] for row in rows}, {42})
        self.assertEqual({row["status"] for row in rows}, {"complete"})

    def test_run_claim_is_global_and_atomic(self):
        run_path = self.directory / "RUN.json"
        run_path.write_text(json.dumps({"status": "active", "deadline_unix": 2**31,
            "final_seed_sealed": True, "consumed_trials": [], "training_branches": []}))
        first = freeze.reserve_final_campaign(run_path, self.directory / "first", {"games": 1000})
        with self.assertRaisesRegex(freeze.FreezeError, "already recorded"):
            freeze.reserve_final_campaign(run_path, self.directory / "second", {"games": 2000})
        freeze.update_final_campaign(run_path, first, "frozen", {"freeze_sha256": "a" * 64})
        freeze.update_final_campaign(run_path, first, "starting", seeded=True)
        recorded = freeze.read_json(run_path)
        self.assertFalse(recorded["final_seed_sealed"])
        freeze.update_final_campaign(run_path, first, "running", {"schedule_pid": 123}, seeded=True)
        freeze.update_final_campaign(run_path, first, "complete", {"finished_at_utc": "now"}, seeded=True)
        self.assertEqual(freeze.read_json(run_path)["final_campaign"]["status"], "complete")

    def test_validation_seeds_are_excluded_and_empty_failed_attempts_are_not_data(self):
        run_path = self.directory / "seed-audit-RUN.json"
        validation_ids = [1234, (1 << 32) + 5678]
        run_path.write_text(json.dumps({"consumed_trials": [], "validation_setup_ids": validation_ids,
            "failed_attempts": [{"master": freeze.MASTER, "records": 0, "output": str(self.directory / "empty")}] }))
        seeds, receipts = freeze.explored_ids(run_path)
        self.assertEqual(seeds, set(validation_ids))
        self.assertEqual(receipts[0]["source"], "RUN.json:validation_setup_ids")

    def test_branch_two_registry_collects_setup_ids_from_all_groups(self):
        groups = {}
        for offset, name in enumerate(("base_train", "base_dev", "dagger_train", "dagger_dev")):
            path = self.directory / f"{name}.bin"
            path.write_bytes((100 + offset).to_bytes(8, "little") + bytes(freeze.ROW_SIZE - 8))
            groups[name] = [{"source": str(path), "source_sha256": freeze.sha(path), "rows": 1}]
        registry_path = self.directory / "branch-registry.json"
        registry_path.write_text(json.dumps({"schema": "sprint48-dagger-branch2-registry-v1",
            "groups": groups}))
        ids, receipts = freeze.corpus_ids([registry_path])
        self.assertEqual(ids, {100, 101, 102, 103})
        self.assertEqual({receipt.get("group") for receipt in receipts}, set(groups))

    def test_branch_two_multi_entry_groups_collect_every_mixed_size_source(self):
        groups = {}
        expected_ids = set()
        for index, name in enumerate(("base_train", "base_dev", "dagger_train", "dagger_dev")):
            entries = []
            for row_size, setup_id in ((freeze.ROW_SIZE, 1000 + index * 2),
                                       (freeze.RICH_ROW_SIZE, 1001 + index * 2)):
                path = self.directory / f"{name}-{row_size}.bin"
                path.write_bytes(setup_id.to_bytes(8, "little") + bytes(row_size - 8))
                entries.append({"source": str(path), "source_sha256": freeze.sha(path),
                    "rows": 1, "row_bytes": row_size})
                expected_ids.add(setup_id)
            groups[name] = entries
        registry_path = self.directory / "branch-multi-registry.json"
        registry_path.write_text(json.dumps({"schema": "sprint48-dagger-branch2-registry-v1",
            "groups": groups}))
        ids, receipts = freeze.corpus_ids([registry_path])
        self.assertEqual(ids, expected_ids)
        self.assertEqual(len(receipts), 8)
        self.assertEqual({receipt["group"] for receipt in receipts}, set(groups))
        self.assertEqual({receipt["row_bytes"] for receipt in receipts},
            {freeze.ROW_SIZE, freeze.RICH_ROW_SIZE})

    def test_legacy_registry_accepts_hash_bound_rich_row_size(self):
        registry = {}
        for split, setup_id in (("train", 201), ("dev", 202)):
            path = self.directory / f"{split}-rich.bin"
            path.write_bytes(setup_id.to_bytes(8, "little") + bytes(freeze.RICH_ROW_SIZE - 8))
            registry[split] = [{"source": str(path), "source_sha256": freeze.sha(path),
                "rows": 1, "row_bytes": freeze.RICH_ROW_SIZE}]
        registry_path = self.directory / "rich-registry.json"
        registry_path.write_text(json.dumps(registry))
        ids, receipts = freeze.corpus_ids([registry_path])
        self.assertEqual(ids, {201, 202})
        self.assertEqual({entry["row_bytes"] for entry in receipts}, {freeze.RICH_ROW_SIZE})

    def test_branch_two_registry_rejects_missing_groups_and_unknown_schema(self):
        registry_path = self.directory / "invalid-branch-registry.json"
        schema = "sprint48-dagger-branch2-registry-v1"
        registry_path.write_text(json.dumps({"schema": schema, "groups": {}}))
        with self.assertRaisesRegex(freeze.FreezeError, "groups must be exactly"):
            freeze.corpus_ids([registry_path])
        registry_path.write_text(json.dumps({"schema": "unknown-v1", "train": [], "dev": []}))
        with self.assertRaisesRegex(freeze.FreezeError, "unsupported corpus registry schema"):
            freeze.corpus_ids([registry_path])

    def test_rich_archive_rows_extract_setup_ids_across_chunk_boundaries(self):
        archive = self.directory / "tiny-archive"
        (archive / "chunks").mkdir(parents=True)
        raw = b"".join(value.to_bytes(8, "little") + bytes(freeze.RICH_ROW_SIZE - 8)
            for value in (501, 502))
        chunks = []
        for index, block in enumerate((raw[:613], raw[613:])):
            relative = f"chunks/{index}.gz"
            path = archive / relative
            with gzip.open(path, "wb") as stream:
                stream.write(block)
            chunks.append({"path": relative, "compressed_sha256": freeze.sha(path),
                "uncompressed_sha256": hashlib.sha256(block).hexdigest(), "bytes": len(block)})
        manifest = {"files": [{"path": "first/train/rows.bin", "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "chunks": chunks}]}
        ids, receipt = freeze._archive_member_ids(archive, manifest, "first/train/rows.bin", freeze.RICH_ROW_SIZE)
        self.assertEqual(ids, {501, 502})
        self.assertEqual(receipt["rows"], 2)
        self.assertEqual(receipt["row_bytes"], freeze.RICH_ROW_SIZE)

    def test_candidate_ancestry_receipt_binds_every_historical_setup_source(self):
        run = freeze.read_json(ROOT / "research/sprint48/RUN.json")
        checkpoint = ROOT / "local/research/sprint48/refit-01/fit/model.pt"
        ids, receipts = freeze._candidate_ancestry(run, checkpoint)
        ancestry = freeze.read_json(ROOT / freeze.ANCESTRY_SETUP_IDS_PATH)
        self.assertEqual(len(ids), ancestry["validation"]["unique_ancestry_full_ids"])
        receipt = receipts[0]
        self.assertEqual(receipt["sha256"], freeze.ANCESTRY_SETUP_IDS_SHA256)
        self.assertEqual(receipt["source_count"], len(ancestry["extra_ancestor_corpora"])
            + len(ancestry["historical_selection_screens"]))

    def test_collection_jobs_block_while_active_and_audit_complete_receipts(self):
        active = {"data_collection_jobs": [{"status": "running"}]}
        with self.assertRaisesRegex(freeze.FreezeError, "data_collection_jobs job is running"):
            freeze._collection_ids(active)

        output = self.directory / "completed-collection"
        (output / "train").mkdir(parents=True)
        master = 17710000000
        seed = freeze.setup_seed(master, 0)
        (output / "train/arena").mkdir()
        raw_path = output / "train/arena/games.jsonl"
        raw_path.write_text(json.dumps({"master": master}) + "\n" + "\n".join(
            json.dumps({"block": 0, "setup_seed": seed, "rotation": rotation}) for rotation in (0, 1)) + "\n")
        setup_path = output / "train/setup_ids.txt"
        setup_path.write_text(f"{seed}\n")
        source = {"split": "train", "status": "complete", "raw": str(raw_path),
            "raw_sha256": freeze.sha(raw_path), "source_master": master, "games": 2,
            "paired_setups": 1, "setup_ids_sha256": freeze.sha(setup_path)}
        source_run = {"schema": "sprint48-dagger-source-collection-v1", "status": "complete",
            "sources": [source]}
        (output / "run.json").write_text(json.dumps(source_run))
        ids, receipts = freeze._collection_ids({"data_collection_jobs": [{"status": "complete",
            "output": str(output)}]})
        self.assertEqual(ids, {seed})
        self.assertEqual(receipts[0]["splits"][0]["setup_ids"], 1)

        labels = self.directory / "completed-labels"
        labels.mkdir()
        label_ids_path = labels / "setup_ids.txt"
        label_ids_path.write_text("700\n701\n")
        registry_path = labels / "registry-entries.json"
        registry_path.write_text(json.dumps({"schema": "sprint48-offline-label-registry-v1",
            "setup_ids_file": label_ids_path.name, "setup_ids_sha256": freeze.sha(label_ids_path),
            "setup_count": 2}))
        label_run = {"schema": "sprint48-offline-label-run-result-v1", "status": "complete",
            "registry": str(registry_path), "registry_sha256": freeze.sha(registry_path)}
        (labels / "run.json").write_text(json.dumps(label_run))
        label_audit, label_receipts = freeze._collection_ids({"offline_label_jobs": [{
            "status": "complete", "output": str(labels), "registry_sha256": freeze.sha(registry_path)}]})
        self.assertEqual(label_audit, {700, 701})
        self.assertEqual(label_receipts[0]["setup_ids"], 2)

    def test_freeze_writer_requires_the_global_run_claim(self):
        run_path = self.directory / "unclaimed-RUN.json"
        run_path.write_text(json.dumps({"status": "active"}))
        path = self.directory / "final-freeze.json"
        with self.assertRaisesRegex(freeze.FreezeError, "must reserve this output"):
            freeze.write_once(path, self.manifest, run_path)
        self.assertFalse(path.exists())

    def test_deadline_kills_owned_schedule_and_keeps_noncomplete_receipt(self):
        run_path = self.directory / "deadline-RUN.json"
        run_path.write_text(json.dumps({"status": "active", "deadline_unix": time.time() + 60,
            "final_seed_sealed": True, "consumed_trials": [], "training_branches": []}))
        output = self.directory / "deadline-output"
        output.mkdir()
        campaign_id = freeze.reserve_final_campaign(run_path, output, {"games": 1000})
        freeze.update_final_campaign(run_path, campaign_id, "frozen")
        receipt = {"output": str(output), "status": "frozen"}
        command = [sys.executable, "-c", "import time; time.sleep(5)"]
        with self.assertRaisesRegex(TimeoutError, "fixed campaign deadline"):
            execute_schedule(command, output / "arena-command", time.time() + .15,
                receipt, campaign_id, 123, utc_now(), run_path)
        result = json.loads((output / "arena-command/exit.json").read_text())
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(receipt["status"], "complete")
        self.assertEqual(freeze.read_json(run_path)["final_campaign"]["status"], "running")
        freeze.update_final_campaign(run_path, campaign_id, "failed", {"error": "deadline"}, seeded=True)

    def test_schedule_start_failures_do_not_consume_final_seed(self):
        for failure in ("mkdir", "log-open", "popen"):
            with self.subTest(failure=failure):
                run_path = self.directory / f"{failure}-RUN.json"
                run_path.write_text(json.dumps({"status": "active", "deadline_unix": time.time() + 60,
                    "final_seed_sealed": True, "consumed_trials": [], "training_branches": []}))
                output = self.directory / f"{failure}-output"
                output.mkdir()
                campaign_id = freeze.reserve_final_campaign(run_path, output, {"games": 1000})
                freeze.update_final_campaign(run_path, campaign_id, "frozen")
                directory = output / "arena-command"
                if failure == "mkdir":
                    directory.mkdir()
                elif failure == "log-open":
                    directory.mkdir()
                    (directory / "output.log").mkdir()
                receipt = {"output": str(output), "status": "frozen"}
                command = [sys.executable, "-c", "pass"]
                popen_patch = (mock.patch("run_final.subprocess.Popen", side_effect=OSError("spawn failed"))
                    if failure == "popen" else mock.patch("run_final.subprocess.Popen"))
                with popen_patch as popen, self.assertRaises((OSError, FileExistsError, IsADirectoryError)):
                    execute_schedule(command, directory, time.time() + 60, receipt,
                        campaign_id, 123, utc_now(), run_path)
                if failure != "popen":
                    popen.assert_not_called()
                self.assertNotIn("schedule_pid", receipt)
                freeze.update_final_campaign(run_path, campaign_id, "failed",
                    {"error": f"{failure} failed"}, seeded=receipt.get("schedule_pid") is not None)
                recorded = freeze.read_json(run_path)
                self.assertTrue(recorded["final_seed_sealed"])
                self.assertEqual(recorded["final_campaign"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
