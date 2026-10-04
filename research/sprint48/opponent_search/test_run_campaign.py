"""CPU-only checks for the one-shot 6400-search campaign guard."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
import run_campaign as campaign
NATIVE = ROOT / "benchmarks/strength/native"
SCHEDULE_SPEC = importlib.util.spec_from_file_location(
    "opponent_search_campaign_test_schedule", Path(__file__).with_name("schedule.py"))
schedule = importlib.util.module_from_spec(SCHEDULE_SPEC)
SCHEDULE_SPEC.loader.exec_module(schedule)


def valid_followup() -> dict:
    return {
        "schema": "sprint48-followup-plan-v1", "status": "active",
        "deadline_utc": "2099-10-05T19:35:52Z",
        "canonical_diagnostic": {
            "status": "complete", "driver_pid": 38974, "service_pid": 38978,
            "compare_pid": 38980,
            "output": "local/research/sprint48/final-canonical-diagnostic-17791000000"},
        "opponent_search": {
            "status": "preparing_harness",
            "candidate_checkpoint_sha256": campaign.CHECKPOINT_SHA256,
            "candidate_search": campaign.expected_candidate_search(),
            "opponent_revision": campaign.AZ_REVISION,
            "opponent_checkpoint_sha256": campaign.AZ_CHECKPOINT_SHA256,
            "opponent_simulations": 6400, "games": 1000, "paired_blocks": 500,
            "master": campaign.MASTER, "adaptive_stopping": False,
            "implementation_budget_seconds": 7200,
            "job_budget_seconds": campaign.DEADLINE_BUDGET_SECONDS,
            "exclusions_sha256": campaign.EXCLUSIONS_SHA256,
            "seed_audit": "local/research/sprint48/opponent-search-preflight/setup-audit.json",
        },
    }


class CampaignDriverTests(unittest.TestCase):
    def test_requires_all_canonical_processes_to_stop(self):
        doc = valid_followup()
        checked = campaign.require_canonical_stopped(doc, lambda _pid: False)
        self.assertEqual(checked["pids"], campaign.CANONICAL_PIDS)
        with self.assertRaisesRegex(RuntimeError, "still active"):
            campaign.require_canonical_stopped(doc, lambda pid: pid == 38978)
        doc["canonical_diagnostic"]["service_pid"] = 22
        with self.assertRaisesRegex(ValueError, "PIDs differ"):
            campaign.require_canonical_stopped(doc, lambda _pid: False)

    def test_plan_must_keep_registered_fixed_count_master_and_budget(self):
        doc = valid_followup()
        self.assertEqual(campaign.validate_followup_plan(doc)["plan"]["master"], campaign.MASTER)
        doc["opponent_search"]["games"] = 2
        with self.assertRaisesRegex(ValueError, "differs from the registered plan at games"):
            campaign.validate_followup_plan(doc)
        doc = valid_followup()
        doc["opponent_search"]["reservation"] = {"seed_consumed": False}
        with self.assertRaisesRegex(ValueError, "already has a reservation"):
            campaign.validate_followup_plan(doc)

    def test_reservation_is_one_shot_and_seed_consumption_is_monotone(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48") as temp:
            path = Path(temp) / "FOLLOWUP.json"
            path.write_text(json.dumps(valid_followup()))
            reservation = {"profile": campaign.PROFILE, "master": campaign.MASTER,
                "games": campaign.GAMES, "schedule_output": str((Path(temp) / "schedule").resolve()),
                "opponent_simulations": campaign.AZ_SIMULATIONS,
                "candidate_search": campaign.expected_candidate_search(),
                "candidate_checkpoint_sha256": campaign.CHECKPOINT_SHA256,
                "candidate_descriptor_sha256": "d" * 64}
            digest = campaign.reserve_followup(path, reservation)
            document = json.loads(path.read_text())
            opponent = document["opponent_search"]
            self.assertEqual(opponent["reservation"], reservation)
            self.assertEqual(opponent["reservation_sha256"], digest)
            self.assertFalse(opponent["seed_consumed"])
            with self.assertRaisesRegex(ValueError, "already has a reservation"):
                campaign.reserve_followup(path, reservation)
            campaign.update_reservation(path, digest, seed_consumed=True, status="running",
                                        fields={"schedule_pid": 1234})
            campaign.update_reservation(path, digest, seed_consumed=False, status="failed")
            final = json.loads(path.read_text())["opponent_search"]
            self.assertTrue(final["seed_consumed"])
            self.assertEqual(final["status"], "failed")
            self.assertEqual(final["schedule_pid"], 1234)

    def test_reservation_digest_binds_descriptor_service_binaries_and_sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48") as temp:
            base = Path(temp)
            checkpoint = base / "candidate.pt"
            checkpoint.write_bytes(b"checkpoint")
            descriptor = base / "model.bin"
            descriptor.write_bytes(b"descriptor")
            model_pt = base / "model.pt"
            model_pt.write_bytes(b"model")
            export = base / "export.json"
            export.write_text("{}")
            service_receipt = base / "service.json"
            service_receipt.write_text("{}")
            parity = base / "parity.json"
            parity.write_text("{}")
            sources = base / "sources"
            sources.mkdir()
            source = sources / "run.py"
            source.write_text("source")
            binaries = {}
            for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
                path = base / name
                path.write_bytes(name.encode())
                binaries[name] = {"path": str(path), "sha256": campaign.sha(path)}
            bundle = {
                "sources": {"campaign-source:run.py": {"path": str(source), "sha256": campaign.sha(source)}},
                "binaries": binaries,
                "checkpoint": {"path": str(checkpoint), "sha256": campaign.sha(checkpoint)},
                "exported_artifacts": {
                    "model_pt": {"path": str(model_pt), "sha256": campaign.sha(model_pt)},
                    "descriptor": {"path": str(descriptor), "sha256": campaign.sha(descriptor)},
                    "export_receipt": {"path": str(export), "sha256": campaign.sha(export)},
                    "parity_input": {"path": str(parity), "sha256": campaign.sha(parity)},
                    "parity_receipt": {"path": str(parity), "sha256": campaign.sha(parity)},
                },
                "service_receipt": {"path": str(service_receipt), "sha256": campaign.sha(service_receipt)},
                "manifest_path": str(base / "bundle.json"), "manifest_sha256": "f" * 64,
            }
            reservation = campaign.build_reservation(base / "schedule", campaign.sha(descriptor), descriptor, bundle)
            self.assertEqual(reservation["candidate_descriptor_sha256"], campaign.sha(descriptor))
            self.assertEqual(reservation["candidate_artifacts"]["service"]["backend"], "mps")
            self.assertEqual(reservation["candidate_artifacts"]["service"]["slot"], 13)
            self.assertEqual(reservation["source_sha256"], {"run.py": campaign.sha(source)})
            self.assertEqual(campaign.hash_value(reservation),
                             campaign.hash_value(json.loads(json.dumps(reservation))))

    def test_generated_reservation_matches_scheduler_bundle_validator(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local/research/sprint48") as temp:
            base = Path(temp)
            def file(name: str, data: bytes) -> Path:
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return path

            checkpoint = file("input/candidate.pt", b"candidate")
            model_pt = file("service/13/model.pt", b"torch bytes")
            descriptor = file("service/13/model.bin", b"descriptor")
            export = file("service/13/export.json", b"{}")
            parity_input = file("service/13/parity.json", b"fixture")
            service_receipt = file("service/run.json", b"{}")
            parity_receipt = file("parity-command/result.json", b"{}")
            source = file("provenance/source.py", b"source")
            bins = {}
            for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
                path = file(f"binaries/{name}", name.encode())
                bins[name] = {"path": str(path), "sha256": campaign.sha(path)}
            source_row = {"path": str(source), "sha256": campaign.sha(source)}
            export.write_text(json.dumps({"checkpoint_sha256": campaign.sha(checkpoint),
                                          "descriptor_sha256": campaign.sha(descriptor)}))
            service_artifacts = {"backend": "mps", "batch": 32, "delay_ms": 1,
                "port": 19760, "fast_entities": True, "slot": 13,
                "checkpoint_path": str(checkpoint), "checkpoint_sha256": campaign.sha(checkpoint),
                "model_pt_path": str(model_pt), "model_pt_sha256": campaign.sha(model_pt),
                "descriptor_path": str(descriptor), "descriptor_sha256": campaign.sha(descriptor),
                "export_receipt_path": str(export), "export_receipt_sha256": campaign.sha(export),
                "service_receipt_path": str(service_receipt), "service_receipt_sha256": campaign.sha(service_receipt),
                "parity_input_path": str(parity_input), "parity_input_sha256": campaign.sha(parity_input),
                "parity_receipt_path": str(parity_receipt), "parity_receipt_sha256": campaign.sha(parity_receipt)}
            source_map = {"provenance/source.py": campaign.sha(source)}
            manifest_path = base / "provenance/bundle-manifest.json"
            bundle = {"sources": {"frozen-source:provenance/source.py": source_row},
                "binaries": bins, "checkpoint": {"path": str(checkpoint), "sha256": campaign.sha(checkpoint)},
                "exported_artifacts": {
                    "model_pt": {"path": str(model_pt), "sha256": campaign.sha(model_pt)},
                    "descriptor": {"path": str(descriptor), "sha256": campaign.sha(descriptor)},
                    "export_receipt": {"path": str(export), "sha256": campaign.sha(export)},
                    "parity_input": {"path": str(parity_input), "sha256": campaign.sha(parity_input)},
                    "parity_receipt": {"path": str(parity_receipt), "sha256": campaign.sha(parity_receipt)}},
                "service_receipt": {"path": str(service_receipt), "sha256": campaign.sha(service_receipt)},
                "manifest_path": str(manifest_path), "manifest_sha256": "",
                "source_sha256": source_map}
            manifest_path.write_text(json.dumps({"source_sha256": source_map,
                "files": {"sources": bundle["sources"]}}))
            bundle["manifest_sha256"] = campaign.sha(manifest_path)
            with mock.patch.object(campaign, "CHECKPOINT_SHA256", campaign.sha(checkpoint)):
                reservation = campaign.build_reservation(base / "schedule", campaign.sha(descriptor),
                                                           descriptor, bundle)
            schedule.validate_bundle(reservation, descriptor, Path(bins["native_policy_worker"]["path"]),
                                     Path(bins["strength_worker"]["path"]))
            self.assertEqual(reservation["service"], reservation["candidate_artifacts"]["service"])

    def test_copy_provenance_binds_freeze_file_bytes_and_keeps_semantic_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)

            def file(name: str, data: bytes = b"artifact") -> Path:
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return path

            repo = base / "repo"
            frozen_source = repo / "tests/frozen.rs"
            frozen_source.parent.mkdir(parents=True)
            frozen_source.write_bytes(b"frozen source")
            semantic_digest = "freeze-semantic-digest"
            freeze_path = file("final-freeze.json", json.dumps({"freeze_sha256": semantic_digest}).encode())
            decision_path = file("FINAL_DECISION.json", b"decision")
            checkpoint = file("runtime.pt", b"checkpoint")
            binaries = base / "release/examples"
            for name in ("native_policy_worker", "strength_worker", "transfer_parity"):
                file(f"release/examples/{name}", name.encode())
            extra_paths = [file(f"sources/source-{index}.py") for index in range(11)]
            output = base / "campaign"
            freeze = {"freeze_sha256": semantic_digest,
                "source_sha256": {"tests/frozen.rs": campaign.sha(frozen_source)}}
            decision = {"freeze_sha256": semantic_digest}
            patches = {
                "ROOT": repo, "FREEZE_PATH": freeze_path, "DECISION_PATH": decision_path,
                "CHECKPOINT_SHA256": campaign.sha(checkpoint),
                "RUNNER": extra_paths[0], "SCHEDULE": extra_paths[1],
                "RUNTIME_SOURCE": extra_paths[2], "SERVICE_SOURCE": extra_paths[3],
                "EXPORT_SOURCE": extra_paths[4], "EVIDENCE_SOURCE": extra_paths[5],
                "REPLAY": extra_paths[6], "SUMMARIZE": extra_paths[7],
                "BUILD_VALIDATION": extra_paths[8], "PREFLIGHT": extra_paths[9],
                "EXCLUSIONS": extra_paths[10],
            }
            with mock.patch.multiple(campaign, **patches):
                copied = campaign.copy_provenance(output, freeze, decision, checkpoint, binaries)

            copied_freeze = Path(copied["freeze_path"])
            self.assertEqual(copied["freeze_sha256"], semantic_digest)
            self.assertEqual(copied["freeze_file_sha256"], campaign.sha(freeze_path))
            self.assertEqual(campaign.sha(copied_freeze), campaign.sha(freeze_path))
            self.assertNotEqual(copied["freeze_file_sha256"], semantic_digest)


if __name__ == "__main__":
    unittest.main()
