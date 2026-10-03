#!/usr/bin/env python3
"""Preflight, freeze, and verify the Sprint 48 final native evaluation.

``check`` audits a proposal without writing a freeze. ``freeze`` writes exactly
one read-only ``final-freeze.json``. Neither command serves a model or starts
games. The frozen game count and master cannot change after outcomes start.

Proposal JSON fields::

    {
      "candidate": {"checkpoint":"...pt", "descriptor":"...bin",
        "export_receipt":"...export.json", "policy_binary":"...worker",
        "strength_binary":"...worker", "parity_binary":"...parity"},
      "search": {"algorithm":"gumbel", "iterations":800, "depth":16,
        "world_pool":3, "chance_universes":0, "dynamic_fpu":false,
        "gumbel_max_considered":16, "root_only":false},
      "service": {"backend":"mps", "batch":32, "delay_ms":1,
        "port":19720, "fast_entities":true},
      "games":2000
    }

Example preflight (repeat ``--corpus-registry`` for every corpus used by the
candidate)::

    python3 research/sprint48/freeze.py check proposal.json \
      --output-root local/research/sprint48 \
      --corpus-registry local/research/architecture-pivots/expanded-data.json \
      --run-json research/sprint48/RUN.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import mmap
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AZ_REVISION = "32a27ac1f85d5de2766cc5f60c2bf04e557f7836"
AZ_CHECKPOINT = "6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07"
AZ_EXTERNAL_CONFIG = {"numMCTSSims": 800, "fpu": 0.0593, "universes": 3,
    "cpuct": 0.8, "prob_fullMCTS": 1.0, "forced_playouts": False, "no_mem_optim": False}
MASTER = 17790000000
GAME_COUNTS = (1000, 2000, 4000)
ROW_SIZE = 2232  # research/flywheel_model.py: setup is the first <u8 field.
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PROFILE = "alphazero-native-32a27ac-v1"


class FreezeError(ValueError):
    pass


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_value(value) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise FreezeError(f"cannot read {path}: {error}") from error


def rooted(path: str | Path) -> Path:
    path = Path(path)
    return (path if path.is_absolute() else ROOT / path).resolve(strict=True)


def identity(value: str, label: str, executable=False) -> dict:
    path = rooted(value)
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise FreezeError(f"{label} is not a usable file: {path}")
    return {"path": str(path), "sha256": sha(path)}


def _proposal(proposal: dict) -> tuple[dict, dict, dict, int]:
    if not isinstance(proposal, dict) or proposal.get("schema") != "sprint48-final-proposal-v1":
        raise FreezeError("proposal schema must be sprint48-final-proposal-v1")
    if set(proposal) != {"schema", "candidate", "search", "service", "games"}:
        raise FreezeError("proposal has missing or extra fields")
    candidate, search, service, games = (proposal[k] for k in ("candidate", "search", "service", "games"))
    candidate_keys = {"checkpoint", "descriptor", "export_receipt", "policy_binary", "strength_binary", "parity_binary"}
    search_keys = {"algorithm", "iterations", "depth", "world_pool", "chance_universes", "dynamic_fpu", "gumbel_max_considered", "root_only"}
    service_keys = {"backend", "batch", "delay_ms", "port", "fast_entities"}
    if not isinstance(candidate, dict) or set(candidate) != candidate_keys:
        raise FreezeError("candidate must name checkpoint, descriptor, export receipt, and three binaries")
    if any(not isinstance(v, str) or not v for v in candidate.values()):
        raise FreezeError("candidate paths must be non-empty strings")
    if not isinstance(search, dict) or set(search) != search_keys:
        raise FreezeError("search must specify algorithm, budget, depth, world pool, cap, and root_only")
    if search["algorithm"] not in ("puct", "gumbel"):
        raise FreezeError("search algorithm must be puct or gumbel")
    if not isinstance(search["iterations"], int) or not 0 <= search["iterations"] <= 0xFFFFFFFF:
        raise FreezeError("iterations must be in 0..=4294967295")
    if not isinstance(search["depth"], int) or not 1 <= search["depth"] <= 124:
        raise FreezeError("depth must be in 1..=124")
    if not isinstance(search["world_pool"], int) or not 0 <= search["world_pool"] <= 64:
        raise FreezeError("world_pool must be in 0..=64")
    if not isinstance(search["chance_universes"], int) or not 0 <= search["chance_universes"] <= 64:
        raise FreezeError("chance_universes must be in 0..=64")
    if not isinstance(search["dynamic_fpu"], bool):
        raise FreezeError("dynamic_fpu must be boolean")
    cap = search["gumbel_max_considered"]
    if search["algorithm"] == "gumbel":
        if not isinstance(cap, int) or not 1 <= cap <= 81:
            raise FreezeError("Gumbel cap must be in 1..=81")
    elif cap is not None:
        raise FreezeError("PUCT must set gumbel_max_considered to null")
    if not isinstance(search["root_only"], bool):
        raise FreezeError("root_only must be boolean")
    if not isinstance(service, dict) or set(service) != service_keys:
        raise FreezeError("service must specify backend, batch, delay, port, and fast_entities")
    if service["backend"] not in ("cpu", "mps") or service["fast_entities"] is not True:
        raise FreezeError("service backend or fast_entities value is invalid")
    if not isinstance(service["batch"], int) or not 1 <= service["batch"] <= 256:
        raise FreezeError("service batch must be in 1..=256")
    if not isinstance(service["delay_ms"], int) or not 1 <= service["delay_ms"] <= 100:
        raise FreezeError("service delay_ms must be in 1..=100")
    if not isinstance(service["port"], int) or not 1 <= service["port"] <= 65535:
        raise FreezeError("service port must be in 1..=65535")
    if games not in GAME_COUNTS:
        raise FreezeError("games must be exactly 1000, 2000, or 4000")
    return candidate, search, service, games


def final_setup_ids(games: int) -> list[int]:
    """Return referee seeds after its low-32-bit conversion."""
    if games not in GAME_COUNTS:
        raise FreezeError("unsupported final game count")
    seeds = []
    for block in range(games // 2):
        seeds.append(setup_seed(MASTER, block) & 0xFFFFFFFF)
    if len(set(seeds)) != len(seeds):
        raise FreezeError("final setup stream has low-32-bit collisions")
    return seeds


def setup_seed(master: int, block: int) -> int:
    key = f"native-v1:{master}:setup:{block}:0".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "little")


def check_disjoint(selected: list[int], excluded: set[int]) -> None:
    overlap = set(selected) & {value & 0xFFFFFFFF for value in excluded}
    if overlap:
        raise FreezeError(f"final setup IDs overlap prior data: {sorted(overlap)[:8]}")


def corpus_ids(registry_paths: list[Path]) -> tuple[set[int], list[dict]]:
    ids, receipts, seen = set(), [], set()
    if not registry_paths:
        raise FreezeError("at least one train/dev corpus registry is required")
    for raw_path in registry_paths:
        registry_path = rooted(raw_path)
        if registry_path in seen:
            raise FreezeError(f"duplicate corpus registry: {registry_path}")
        seen.add(registry_path)
        registry = read_json(registry_path)
        for split in ("train", "dev"):
            entries = registry.get(split)
            if not isinstance(entries, list) or not entries:
                raise FreezeError(f"registry must contain non-empty {split} entries")
            for entry in entries:
                path = rooted(entry["source"])
                if sha(path) != entry.get("source_sha256"):
                    raise FreezeError(f"corpus hash differs from registry: {path}")
                rows = entry.get("rows")
                if not isinstance(rows, int) or rows < 1 or path.stat().st_size != rows * ROW_SIZE:
                    raise FreezeError(f"corpus row count or packed-row size is invalid: {path}")
                source_ids = set()
                with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    for offset in range(0, len(data), ROW_SIZE):
                        source_ids.add(int.from_bytes(data[offset:offset + 8], "little"))
                ids.update(source_ids)
                receipts.append({"split": split, "path": str(path), "sha256": sha(path),
                                 "rows": rows, "setup_ids": len(source_ids)})
    return ids, receipts


def _raw_files(output: Path) -> list[Path]:
    for candidate in (output / "arena/games.jsonl", output / "games.jsonl", output / "arena.jsonl"):
        if candidate.is_file():
            return [candidate]
    for directory in (output / "arena", output):
        files = sorted(directory.glob("shard-*.jsonl")) if directory.is_dir() else []
        if files:
            return files
    return []


def explored_ids(run_path: Path) -> tuple[set[int], list[dict]]:
    run_path = rooted(run_path)
    run = read_json(run_path)
    ids, receipts = set(), []
    validation_ids = run.get("validation_setup_ids", [])
    if not isinstance(validation_ids, list) or any(not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFFFFFFFFFF
            for seed in validation_ids):
        raise FreezeError("RUN.json validation_setup_ids must be a list of 64-bit seeds")
    if validation_ids:
        ids.update(validation_ids)
        receipts.append({"source": "RUN.json:validation_setup_ids", "records": len(validation_ids),
            "setup_ids_sha256": hash_value(validation_ids)})
    for trial in run.get("consumed_trials", []):
        if trial.get("status") == "running":
            raise FreezeError("cannot freeze while an exploratory game trial is running")
        master = trial.get("master")
        if not isinstance(master, int) or master == MASTER:
            raise FreezeError("invalid or final master in consumed trials")
        output = Path(trial["output"])
        output = output if output.is_absolute() else ROOT / output
        files = _raw_files(output)
        if not files:
            raise FreezeError(f"no retained game setup IDs for consumed trial: {output}")
        count = 0
        for path in files:
            path_ids = 0
            header = True
            with path.open() as source:
                for line in source:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if header:
                        header = False
                        if row.get("master", master) != master:
                            raise FreezeError(f"schedule master differs from run receipt: {path}")
                    elif "setup_seed" in row:
                        if not isinstance(row.get("block"), int) or int(row["setup_seed"]) != setup_seed(master, row["block"]):
                            raise FreezeError(f"setup ID does not match consumed master/block: {path}")
                        ids.add(int(row["setup_seed"]))
                        count += 1
                        path_ids += 1
            receipts.append({"path": str(path.resolve()), "sha256": sha(path), "records": path_ids})
        if count == 0:
            raise FreezeError(f"consumed trial has no retained setup records: {output}")
    return ids, receipts


def _check_no_final_outcomes(output_root: Path, run: dict) -> None:
    if any(trial.get("master") == MASTER for trial in run.get("consumed_trials", [])):
        raise FreezeError("final master already appears in consumed trials")
    if not output_root.exists():
        return
    for path in output_root.rglob("*.jsonl"):
        if path.name not in ("games.jsonl", "arena.jsonl") and not path.name.startswith("shard-"):
            continue
        try:
            with path.open() as source:
                first = next((line for line in source if line.strip()), "")
            metadata = json.loads(first) if first else {}
        except (OSError, json.JSONDecodeError):
            continue
        if metadata.get("master") == MASTER:
            raise FreezeError(f"final-master outcome already exists: {path}")


def _target(source: Path) -> dict:
    source = rooted(source)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    if revision != AZ_REVISION or dirty:
        raise FreezeError("AlphaZero source is not the pinned clean revision")
    checkpoint = rooted("local/strength/external/alphazero/splendor/pretrained_2players.pt")
    digest = sha(checkpoint)
    if digest != AZ_CHECKPOINT:
        raise FreezeError("AlphaZero checkpoint differs from pinned AlphaZero800")
    return {"source_path": str(source), "revision": revision, "working_tree_clean": True,
            "checkpoint": {"path": str(checkpoint), "sha256": digest},
            "simulations": 800, "profile": PROFILE, "external_config": AZ_EXTERNAL_CONFIG}


def _sources() -> dict[str, str]:
    names = (
        "benchmarks/strength/native/run.py", "benchmarks/strength/native/schedule.py",
        "benchmarks/strength/native/campaign_context.py",
        "benchmarks/strength/native/upstream.py", "benchmarks/strength/native/validate.py",
        "benchmarks/strength/native/replay.py", "benchmarks/strength/native/summarize.py",
        "research/sprint48/run_final.py", "research/training_strategy/runtime.py",
        "research/architecture_pivots/service.py", "research/architecture_pivots/models.py",
        "research/architecture_pivots/export.py", "research/e95/public_model.py",
        "research/flywheel_model.py",
        "research/sprint48/evidence.py", "research/sprint48/freeze.py",
        "crates/splendor-agents/src/environment.rs", "crates/splendor-agents/src/native_environment.rs",
        "crates/splendor-agents/src/neural_search.rs", "crates/splendor-agents/src/transfer.rs",
        "crates/splendor-arena/examples/native_policy_worker.rs",
        "crates/splendor-arena/examples/native_wire/mod.rs",
        "crates/splendor-arena/examples/strength_worker.rs",
        "crates/splendor-arena/examples/transfer_parity.rs",
    )
    return {name: sha(ROOT / name) for name in names}


def build_freeze(proposal: dict, registries: list[Path], run_path: Path,
                 output_root: Path, az_source: Path) -> dict:
    candidate, search, service, games = _proposal(proposal)
    run_path = rooted(run_path)
    output_root = Path(output_root)
    output_root = (output_root if output_root.is_absolute() else ROOT / output_root).resolve()
    run = read_json(run_path)
    if run.get("status") != "active":
        raise FreezeError("campaign is not active")
    if any(branch.get("status") == "running" for branch in run.get("training_branches", [])):
        raise FreezeError("cannot freeze while a training branch is running")
    _check_no_final_outcomes(output_root, run)
    train_ids, corpus_receipts = corpus_ids(registries)
    trial_ids, trial_receipts = explored_ids(run_path)
    final_ids = final_setup_ids(games)
    check_disjoint(final_ids, train_ids | trial_ids)

    files = {key: identity(candidate[key], key.replace("_", " "), key.endswith("binary"))
             for key in ("checkpoint", "descriptor", "export_receipt")}
    binaries = {key: identity(candidate[source], key, True) for key, source in (
        ("native_policy_worker", "policy_binary"), ("strength_worker", "strength_binary"),
        ("transfer_parity", "parity_binary"))}
    receipt = read_json(Path(files["export_receipt"]["path"]))
    if receipt.get("checkpoint_sha256") != files["checkpoint"]["sha256"] or receipt.get("descriptor_sha256") != files["descriptor"]["sha256"]:
        raise FreezeError("export receipt does not bind the selected checkpoint and descriptor")
    service_id = identity("research/architecture_pivots/service.py", "service source")
    target = _target(az_source)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    search = dict(search, cpuct=0.4, fpu_reduction=0.02965, uniform_prior=0.0,
                  gumbel_noise=0.0, root_noise=0.0,
                  gumbel_cvisit=50 if search["algorithm"] == "gumbel" else None,
                  gumbel_cscale=0.1 if search["algorithm"] == "gumbel" else None)
    registries = [rooted(path) for path in registries]
    return {
        "schema": "sprint48-final-freeze-v1", "frozen_at_utc": now,
        "candidate": {**files, "binaries": binaries}, "search": search,
        "service": {**service, "source": service_id}, "target": target,
        "evaluation": {
            "profile": PROFILE, "games": games, "paired_setup_blocks": games // 2,
            "master": MASTER, "adaptive_stopping": False, "sample_size_locked_before_outcomes": True,
            "primary_criterion": {"interval": "two-sided Hoeffding 95% over paired setup blocks",
                "unknown_game_credit_bounds": [0, 1], "radius": "sqrt(log(40)/(2*paired_setup_blocks))",
                "candidate_lower_credit_strictly_greater_than": 0.55},
            "max_no_action_fraction": 0.01, "reject_statuses": ["invalid", "decision_limit"],
            "full_planned_schedule_required": True,
            "caps_sensitivity": {"native_turn_cap_as_unknown": True, "same_paired_blocks": True,
                "report_hoeffding95_interval": True, "primary_threshold_applies_to_caps_sensitivity": False}},
        "seed_audit": {
            "conversion": "SHA256 native-v1:{master}:setup:{block}:0; first 8 bytes little-endian; low 32 bits",
            "setup_ids_low32": final_ids, "setup_ids_sha256": hash_value(final_ids),
            "excluded_low32_sha256": hash_value(sorted({seed & 0xFFFFFFFF for seed in train_ids | trial_ids})),
            "excluded_ids": len(train_ids | trial_ids), "overlap_count": 0,
            "no_prior_final_outcomes_found": True, "output_root_scanned": str(output_root),
            "corpus_registries": [{"path": str(p), "sha256": sha(p)} for p in registries],
            "corpus_sources": corpus_receipts,
            "run_json": {"path": str(run_path), "sha256": sha(run_path)},
            "exploratory_schedules": trial_receipts},
        "source_sha256": _sources(),
    }


def freeze_sha(manifest: dict) -> str:
    body = dict(manifest)
    body.pop("freeze_sha256", None)
    return hash_value(body)


def validate_freeze(freeze: dict) -> None:
    fields = {"schema", "frozen_at_utc", "candidate", "search", "service", "target",
              "evaluation", "seed_audit", "source_sha256", "freeze_sha256"}
    if not isinstance(freeze, dict) or set(freeze) != fields or freeze.get("schema") != "sprint48-final-freeze-v1":
        raise FreezeError("invalid final-freeze schema")
    if freeze["freeze_sha256"] != freeze_sha(freeze):
        raise FreezeError("freeze content hash mismatch")
    try:
        frozen_at = dt.datetime.fromisoformat(freeze["frozen_at_utc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise FreezeError("invalid freeze timestamp") from error
    if frozen_at.tzinfo is None:
        raise FreezeError("freeze timestamp must include its timezone")
    ev, target, search, audit = (freeze[k] for k in ("evaluation", "target", "search", "seed_audit"))
    games = ev.get("games")
    if games not in GAME_COUNTS or ev.get("master") != MASTER or ev.get("paired_setup_blocks") != games // 2:
        raise FreezeError("freeze count, block count, or master is invalid")
    if ev.get("profile") != PROFILE or ev.get("adaptive_stopping") is not False or ev.get("sample_size_locked_before_outcomes") is not True:
        raise FreezeError("freeze profile or stopping rule is invalid")
    if ev.get("primary_criterion") != {"interval": "two-sided Hoeffding 95% over paired setup blocks",
            "unknown_game_credit_bounds": [0, 1], "radius": "sqrt(log(40)/(2*paired_setup_blocks))",
            "candidate_lower_credit_strictly_greater_than": 0.55}:
        raise FreezeError("freeze statistical rule differs from the registered criterion")
    if ev.get("max_no_action_fraction") != 0.01 or ev.get("reject_statuses") != ["invalid", "decision_limit"]:
        raise FreezeError("freeze completion policy is invalid")
    if ev.get("caps_sensitivity") != {"native_turn_cap_as_unknown": True, "same_paired_blocks": True,
            "report_hoeffding95_interval": True, "primary_threshold_applies_to_caps_sensitivity": False}:
        raise FreezeError("freeze caps sensitivity rule is invalid")
    ids = audit.get("setup_ids_low32")
    if not isinstance(ids, list) or len(ids) != games // 2 or len(set(ids)) != len(ids):
        raise FreezeError("freeze setup IDs are incomplete or duplicated")
    if any(not isinstance(x, int) or not 0 <= x <= 0xFFFFFFFF for x in ids) or hash_value(ids) != audit.get("setup_ids_sha256"):
        raise FreezeError("freeze setup ID values or hash are invalid")
    if audit.get("overlap_count") != 0 or audit.get("no_prior_final_outcomes_found") is not True:
        raise FreezeError("freeze seed preflight did not pass")
    if target.get("revision") != AZ_REVISION or target.get("simulations") != 800 or target.get("profile") != PROFILE or target.get("working_tree_clean") is not True:
        raise FreezeError("freeze does not bind unchanged AlphaZero800")
    if target.get("checkpoint", {}).get("sha256") != AZ_CHECKPOINT or target.get("external_config") != AZ_EXTERNAL_CONFIG:
        raise FreezeError("freeze AlphaZero checkpoint hash is invalid")
    if set(freeze["candidate"].get("binaries", {})) != {"native_policy_worker", "strength_worker", "transfer_parity"}:
        raise FreezeError("freeze must bind policy, strength, and parity binaries")
    if search.get("algorithm") not in ("puct", "gumbel") or not isinstance(search.get("root_only"), bool):
        raise FreezeError("freeze search profile is invalid")
    if not isinstance(search.get("iterations"), int) or not 0 <= search["iterations"] <= 0xFFFFFFFF:
        raise FreezeError("freeze simulation count is invalid")
    if not isinstance(search.get("depth"), int) or not 1 <= search["depth"] <= 124:
        raise FreezeError("freeze depth is invalid")
    if not isinstance(search.get("world_pool"), int) or not 0 <= search["world_pool"] <= 64:
        raise FreezeError("freeze world pool is invalid")
    if not isinstance(search.get("chance_universes"), int) or not 0 <= search["chance_universes"] <= 64:
        raise FreezeError("freeze chance universe count is invalid")
    if not isinstance(search.get("dynamic_fpu"), bool):
        raise FreezeError("freeze dynamic_fpu setting is invalid")
    cap = search.get("gumbel_max_considered")
    if (search["algorithm"] == "gumbel" and (not isinstance(cap, int) or not 1 <= cap <= 81)) or (search["algorithm"] == "puct" and cap is not None):
        raise FreezeError("freeze Gumbel cap is invalid")
    constants = {"cpuct": 0.4, "fpu_reduction": 0.02965, "uniform_prior": 0.0,
                 "gumbel_noise": 0.0, "root_noise": 0.0,
                 "gumbel_cvisit": 50 if search["algorithm"] == "gumbel" else None,
                 "gumbel_cscale": 0.1 if search["algorithm"] == "gumbel" else None}
    if any(search.get(k) != v for k, v in constants.items()):
        raise FreezeError("freeze search constants differ from native profile")
    if freeze["service"].get("backend") not in ("cpu", "mps") or freeze["service"].get("fast_entities") is not True:
        raise FreezeError("freeze service configuration is invalid")
    service = freeze["service"]
    if (not isinstance(service.get("batch"), int) or not 1 <= service["batch"] <= 256
            or not isinstance(service.get("delay_ms"), int) or not 1 <= service["delay_ms"] <= 100
            or not isinstance(service.get("port"), int) or not 1 <= service["port"] <= 65535):
        raise FreezeError("freeze service batch, delay, or port is invalid")
    if any(not HEX64.fullmatch(str(digest)) for digest in freeze["source_sha256"].values()):
        raise FreezeError("freeze source fingerprint contains an invalid hash")
    artifacts = [freeze["candidate"].get(k) for k in ("checkpoint", "descriptor", "export_receipt")]
    artifacts += list(freeze["candidate"]["binaries"].values()) + [freeze["service"].get("source"), target.get("checkpoint")]
    if any(not isinstance(x, dict) or not HEX64.fullmatch(str(x.get("sha256", ""))) for x in artifacts):
        raise FreezeError("freeze artifact identity is incomplete")


def validate_outcomes(freeze: dict, metadata: dict, evidence: dict,
                      started_utc: str, games: int) -> bool:
    validate_freeze(freeze)
    frozen = dt.datetime.fromisoformat(freeze["frozen_at_utc"].replace("Z", "+00:00"))
    started = dt.datetime.fromisoformat(started_utc.replace("Z", "+00:00"))
    ev = freeze["evaluation"]
    if started <= frozen:
        raise FreezeError("final outcomes started before the freeze")
    if (games != ev["games"] or metadata.get("games") != ev["games"] or
            metadata.get("campaign_games") != ev["games"] or metadata.get("master") != MASTER):
        raise FreezeError("outcome count or master differs from freeze")
    if metadata.get("ruleset") != PROFILE or metadata.get("planning_profile") != PROFILE or metadata.get("external") != "alphazero":
        raise FreezeError("outcome profile or opponent differs from freeze")
    target = freeze["target"]
    if metadata.get("upstream_revision") != AZ_REVISION or metadata.get("upstream_checkpoint_sha256") != AZ_CHECKPOINT or metadata.get("external_config") != target["external_config"]:
        raise FreezeError("outcome AlphaZero identity differs from freeze")
    candidate = freeze["candidate"]
    for key, value in (("model_sha256", candidate["descriptor"]["sha256"]),
                       ("model_path", candidate["descriptor"]["path"]),
                       ("checkpoint_sha256", candidate["checkpoint"]["sha256"]),
                       ("checkpoint_path", candidate["checkpoint"]["path"]),
                       ("export_receipt_sha256", candidate["export_receipt"]["sha256"])):
        if metadata.get(key) != value:
            raise FreezeError(f"outcome candidate identity differs: {key}")
    search = freeze["search"]
    for key, expected in (("search", search["algorithm"]), ("iterations", search["iterations"]),
                          ("depth", search["depth"]), ("world_pool", search["world_pool"]),
                          ("chance_universes", search["chance_universes"]),
                          ("dynamic_fpu", search["dynamic_fpu"]),
                          ("gumbel_max_considered", search["gumbel_max_considered"]),
                          ("root_only", search["root_only"]), ("cpuct", search["cpuct"]),
                          ("fpu_reduction", search["fpu_reduction"]), ("uniform_prior", search["uniform_prior"])):
        if metadata.get(key) != expected:
            raise FreezeError(f"outcome search differs from freeze: {key}")
    if search["algorithm"] == "gumbel":
        config = {"max_considered": search["gumbel_max_considered"], "cvisit": 50,
                  "cscale": 0.1, "root_noise": 0.0}
        if metadata.get("gumbel_config") != config:
            raise FreezeError("outcome Gumbel constants differ from freeze")
    elif metadata.get("gumbel_config") is not None:
        raise FreezeError("PUCT outcome contains Gumbel settings")
    binaries = candidate["binaries"]
    for name, hash_key, path_key in (("native_policy_worker", "policy_binary_sha256", "policy_binary_path"),
                                    ("strength_worker", "strength_binary_sha256", "strength_binary_path"),
                                    ("transfer_parity", "parity_binary_sha256", "parity_binary_path")):
        if metadata.get(hash_key) != binaries[name]["sha256"] or metadata.get(path_key) != binaries[name]["path"]:
            raise FreezeError(f"outcome binary differs from freeze: {name}")
    service = freeze["service"]
    expected_service = {k: service[k] for k in ("backend", "batch", "delay_ms", "port", "fast_entities")}
    expected_service["source_sha256"] = service["source"]["sha256"]
    if metadata.get("service_config") != expected_service:
        raise FreezeError("outcome service differs from freeze")
    if (metadata.get("freeze_sha256") != freeze["freeze_sha256"] or
            metadata.get("campaign_started_at_utc") != started_utc):
        raise FreezeError("outcome shards do not bind the campaign freeze and start time")
    if any(metadata.get("source_sha256", {}).get(k) != v for k, v in freeze["source_sha256"].items()):
        raise FreezeError("outcome source hashes differ from freeze")
    if not isinstance(evidence, dict) or evidence.get("games") != ev["games"] or evidence.get("evidence_rejections"):
        raise FreezeError("evidence is incomplete or rejected")
    statuses = evidence.get("statuses", {})
    if not isinstance(statuses, dict) or sum(statuses.values()) != ev["games"] or statuses.get("invalid", 0) or statuses.get("decision_limit", 0):
        raise FreezeError("invalid, decision-limit, or missing game records reject evidence")
    if statuses.get("no_legal_action", 0) / ev["games"] > ev["max_no_action_fraction"]:
        raise FreezeError("no-action fraction exceeds one percent")
    for key in ("caps_as_unknown_credit_bounds", "caps_as_unknown_hoeffding95"):
        if not isinstance(evidence.get(key), list) or len(evidence[key]) != 2:
            raise FreezeError("evidence must report caps-as-unknown sensitivity")
    interval = evidence.get("conservative_hoeffding95_missing_envelope")
    if not isinstance(interval, list) or len(interval) != 2:
        raise FreezeError("evidence must report the primary interval")
    return interval[0] > 0.55


def _atomic_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.chmod(temporary, mode)
        with os.fdopen(fd, "w") as output:
            output.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _run_lock(run_path: Path):
    lock_path = Path(run_path).with_name(Path(run_path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def reserve_final_campaign(run_path: Path, output_root: Path, details: dict) -> str:
    """Atomically claim the one final campaign for this RUN.json."""
    run_path = Path(run_path).resolve(strict=True)
    output_root = Path(output_root).resolve()
    handle = _run_lock(run_path)
    try:
        run = read_json(run_path)
        if run.get("status") != "active" or dt.datetime.now(dt.timezone.utc).timestamp() >= run.get("deadline_unix", 0):
            raise FreezeError("campaign is inactive or its fixed deadline has passed")
        if run.get("final_campaign") is not None:
            raise FreezeError("a final campaign is already recorded for this RUN.json")
        if any(trial.get("status") == "running" for trial in run.get("consumed_trials", [])):
            raise FreezeError("an exploratory external trial is still running")
        if any(branch.get("status") == "running" for branch in run.get("training_branches", [])):
            raise FreezeError("a training branch is still running")
        if any(trial.get("master") == MASTER for trial in run.get("consumed_trials", [])):
            raise FreezeError("final master already appears in consumed trials")
        campaign_id = uuid.uuid4().hex
        try:
            stage = str(output_root.relative_to(ROOT))
        except ValueError:
            stage = str(output_root)
        run["final_campaign"] = {"schema": "sprint48-final-campaign-v1", "id": campaign_id,
            "status": "freezing", "output": str(output_root), "claimed_at_utc":
            dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "driver_pid": os.getpid(), **details}
        run["final_seed_sealed"] = True
        run["current_stage"] = stage
        _atomic_json(run_path, run)
        return campaign_id
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def update_final_campaign(run_path: Path, campaign_id: str, status: str,
                          fields: dict | None = None, seeded: bool | None = None) -> dict:
    """Atomically update this campaign record without replacing other RUN fields."""
    allowed = {"freezing": {"frozen", "failed"}, "frozen": {"starting", "failed"},
        "starting": {"running", "failed"}, "running": {"complete", "failed"}}
    run_path = Path(run_path).resolve(strict=True)
    handle = _run_lock(run_path)
    try:
        run = read_json(run_path)
        campaign = run.get("final_campaign")
        if not isinstance(campaign, dict) or campaign.get("id") != campaign_id:
            raise FreezeError("final campaign identity changed in RUN.json")
        current = campaign.get("status")
        if status != current and status not in allowed.get(current, set()):
            raise FreezeError(f"invalid final campaign transition: {current} -> {status}")
        campaign.update(fields or {})
        campaign["status"] = status
        campaign["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        run["final_campaign"] = campaign
        if seeded is not None:
            run["final_seed_sealed"] = not seeded
        _atomic_json(run_path, run)
        return campaign
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def write_once(path: Path, freeze: dict, run_path: Path = ROOT / "research/sprint48/RUN.json") -> None:
    validate_freeze(freeze)
    path = Path(path)
    if path.name != "final-freeze.json" or path.parent.resolve() != Path(freeze["seed_audit"]["output_root_scanned"]).resolve():
        raise FreezeError("write final-freeze.json inside the scanned output root")
    run = read_json(run_path)
    campaign = run.get("final_campaign")
    if (not isinstance(campaign, dict) or campaign.get("status") != "freezing" or
            Path(campaign.get("output", "")).resolve() != path.parent.resolve()):
        raise FreezeError("RUN.json must reserve this output before writing the final freeze")
    if any(path.parent.glob("final-freeze*.json")):
        raise FreezeError("a final freeze already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(json.dumps(freeze, sort_keys=True, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        path.chmod(0o444)
    except BaseException:
        if path.exists():
            path.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command_name in ("check", "freeze"):
        command = sub.add_parser(command_name, help="preflight only" if command_name == "check" else "write the one immutable freeze")
        command.add_argument("proposal", type=Path)
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--corpus-registry", type=Path, action="append", required=True,
                             help="train/dev registry; repeat for every candidate corpus")
        command.add_argument("--run-json", type=Path, required=True)
        command.add_argument("--alphazero-source", type=Path, default=Path("local/strength/external/alphazero"))
        if command_name == "freeze":
            command.add_argument("--output", type=Path, required=True, help="new final-freeze.json path")
    verify = sub.add_parser("verify", help="check an existing freeze's schema and content hash")
    verify.add_argument("freeze", type=Path)
    args = parser.parse_args()
    campaign_id = None
    try:
        if args.command == "verify":
            freeze = read_json(args.freeze)
            validate_freeze(freeze)
        else:
            proposal = read_json(args.proposal)
            output = None
            if args.command == "freeze":
                output = args.output if args.output.is_absolute() else ROOT / args.output
                campaign_id = reserve_final_campaign(args.run_json, args.output_root,
                    {"games": proposal.get("games"), "master": MASTER,
                     "driver_pid": os.getpid(), "source": "freeze.py"})
            freeze = build_freeze(proposal, args.corpus_registry, args.run_json, args.output_root, args.alphazero_source)
            freeze["freeze_sha256"] = freeze_sha(freeze)
            validate_freeze(freeze)
            if args.command == "freeze":
                write_once(output, freeze, args.run_json)
                update_final_campaign(args.run_json, campaign_id, "frozen",
                    {"freeze_path": str(output.resolve()), "freeze_sha256": freeze["freeze_sha256"],
                     "frozen_at_utc": freeze["frozen_at_utc"]})
        print(json.dumps({"status": "valid" if args.command == "verify" else args.command + "_passed",
                          "freeze_sha256": freeze["freeze_sha256"],
                          "games": freeze["evaluation"]["games"], "master": MASTER,
                          "setup_id_sha256": freeze["seed_audit"]["setup_ids_sha256"]}, sort_keys=True))
    except (FreezeError, OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        if campaign_id is not None:
            try:
                update_final_campaign(args.run_json, campaign_id, "failed", {"error": repr(error)})
            except FreezeError:
                pass
        print(f"freeze preflight failed: {error}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
