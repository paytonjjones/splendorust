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
import gzip
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
FIRST_CANDIDATE_ARCHIVE = "research/training_strategy/artifacts/core"
FIRST_CANDIDATE_ARCHIVE_MANIFEST = "c413a533ce69648d5f69994abd0f8458c8f70f33ae2a12b72b351bdd1f7f9399"
ANCESTRY_SETUP_IDS_PATH = "research/sprint48/ANCESTRY_SETUP_IDS.json"
ANCESTRY_SETUP_IDS_SHA256 = "c97f0b56da805ba241028c21cb7108b44a3e7da741cb822e779331a5ad0cf9ff"
RICH_ROW_SIZE = 2600
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
        schema = registry.get("schema")
        if schema is None:
            groups_by_split = {split: [(split, registry.get(split))] for split in ("train", "dev")}
        elif schema == "sprint48-dagger-branch2-registry-v1":
            groups = registry.get("groups")
            expected = {"base_train", "base_dev", "dagger_train", "dagger_dev"}
            if not isinstance(groups, dict) or set(groups) != expected:
                raise FreezeError(f"branch-two registry groups must be exactly {sorted(expected)}")
            groups_by_split = {
                "train": [(name, groups[name]) for name in ("base_train", "dagger_train")],
                "dev": [(name, groups[name]) for name in ("base_dev", "dagger_dev")],
            }
        else:
            raise FreezeError(f"unsupported corpus registry schema: {schema}")
        for split, groups in groups_by_split.items():
            for group_name, entries in groups:
                if not isinstance(entries, list) or not entries:
                    raise FreezeError(f"registry must contain non-empty {group_name} entries")
                for entry in entries:
                    path = rooted(entry["source"])
                    if sha(path) != entry.get("source_sha256"):
                        raise FreezeError(f"corpus hash differs from registry: {path}")
                    rows = entry.get("rows")
                    row_size = entry.get("row_bytes", ROW_SIZE)
                    if (not isinstance(rows, int) or rows < 1 or not isinstance(row_size, int)
                            or row_size < 8 or path.stat().st_size != rows * row_size):
                        raise FreezeError(f"corpus row count or packed-row size is invalid: {path}")
                    source_ids = set()
                    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                        for offset in range(0, len(data), row_size):
                            source_ids.add(int.from_bytes(data[offset:offset + 8], "little"))
                    ids.update(source_ids)
                    receipt = {"split": split, "path": str(path), "sha256": sha(path),
                        "rows": rows, "row_bytes": row_size, "setup_ids": len(source_ids)}
                    if group_name != split:
                        receipt["group"] = group_name
                    receipts.append(receipt)
    return ids, receipts


def _archive_member_ids(archive_root: Path, manifest: dict, member_path: str,
                        row_size: int) -> tuple[set[int], dict]:
    entries = [entry for entry in manifest.get("files", []) if entry.get("path") == member_path]
    if len(entries) != 1:
        raise FreezeError(f"archive member is missing or duplicated: {member_path}")
    entry = entries[0]
    rows, total_bytes = entry.get("bytes"), entry.get("bytes")
    if not isinstance(total_bytes, int) or total_bytes < 1 or total_bytes % row_size:
        raise FreezeError(f"archive row member size is invalid: {member_path}")
    ids, member_digest, bytes_seen, tail = set(), hashlib.sha256(), 0, b""
    chunk_receipts = []
    for chunk in entry.get("chunks", []):
        chunk_path = (archive_root / chunk["path"]).resolve(strict=True)
        if not chunk_path.is_relative_to(archive_root.resolve(strict=True)):
            raise FreezeError(f"archive chunk path escapes archive root: {chunk_path}")
        if sha(chunk_path) != chunk.get("compressed_sha256"):
            raise FreezeError(f"archive compressed chunk hash differs: {chunk_path}")
        chunk_digest, chunk_bytes = hashlib.sha256(), 0
        with gzip.open(chunk_path, "rb") as stream:
            for block in iter(lambda: stream.read(4 << 20), b""):
                chunk_bytes += len(block)
                chunk_digest.update(block)
                member_digest.update(block)
                bytes_seen += len(block)
                data = tail + block
                full = len(data) // row_size
                for offset in range(0, full * row_size, row_size):
                    ids.add(int.from_bytes(data[offset:offset + 8], "little"))
                tail = data[full * row_size:]
        if (chunk_bytes != chunk.get("bytes") or chunk_digest.hexdigest() != chunk.get("uncompressed_sha256")):
            raise FreezeError(f"archive uncompressed chunk differs: {chunk_path}")
        chunk_receipts.append({"path": str(chunk_path), "compressed_sha256": sha(chunk_path),
            "uncompressed_sha256": chunk_digest.hexdigest(), "bytes": chunk_bytes})
    if bytes_seen != total_bytes or tail or member_digest.hexdigest() != entry.get("sha256"):
        raise FreezeError(f"archive member hash or row layout differs: {member_path}")
    rows = total_bytes // row_size
    return ids, {"member": member_path, "sha256": entry["sha256"], "bytes": total_bytes,
        "rows": rows, "row_bytes": row_size, "setup_ids": len(ids), "chunks": chunk_receipts}


def _archive_member_bytes(archive_root: Path, manifest: dict, member_path: str) -> tuple[bytes, dict]:
    entries = [entry for entry in manifest.get("files", []) if entry.get("path") == member_path]
    if len(entries) != 1:
        raise FreezeError(f"archive member is missing or duplicated: {member_path}")
    entry = entries[0]
    content, digest, chunk_receipts = bytearray(), hashlib.sha256(), []
    for chunk in entry.get("chunks", []):
        chunk_path = (archive_root / chunk["path"]).resolve(strict=True)
        if not chunk_path.is_relative_to(archive_root.resolve(strict=True)):
            raise FreezeError(f"archive chunk path escapes archive root: {chunk_path}")
        if sha(chunk_path) != chunk.get("compressed_sha256"):
            raise FreezeError(f"archive compressed chunk hash differs: {chunk_path}")
        chunk_digest, chunk_bytes = hashlib.sha256(), 0
        with gzip.open(chunk_path, "rb") as stream:
            for block in iter(lambda: stream.read(4 << 20), b""):
                chunk_bytes += len(block)
                chunk_digest.update(block)
                digest.update(block)
                content.extend(block)
        if chunk_bytes != chunk.get("bytes") or chunk_digest.hexdigest() != chunk.get("uncompressed_sha256"):
            raise FreezeError(f"archive uncompressed chunk differs: {chunk_path}")
        chunk_receipts.append({"path": str(chunk_path), "compressed_sha256": sha(chunk_path),
            "uncompressed_sha256": chunk_digest.hexdigest(), "bytes": chunk_bytes})
    if len(content) != entry.get("bytes") or digest.hexdigest() != entry.get("sha256"):
        raise FreezeError(f"archive member hash or byte count differs: {member_path}")
    return bytes(content), {"member": member_path, "sha256": entry["sha256"],
        "bytes": len(content), "chunks": chunk_receipts}


def _listed_ids(source: dict) -> tuple[set[int], set[int]]:
    try:
        full = [int(value) for value in source["full_setup_ids"]]
        low = [int(value) for value in source["low32_setup_ids"]]
    except (KeyError, TypeError, ValueError) as error:
        raise FreezeError("ancestry receipt setup-ID arrays are invalid") from error
    if (len(full) != source.get("unique_full_setup_ids") or len(full) != len(set(full))
            or full != sorted(full) or any(not 0 <= value <= 0xFFFFFFFFFFFFFFFF for value in full)):
        raise FreezeError("ancestry full setup-ID list is invalid")
    if (len(low) != source.get("unique_low32_setup_ids") or len(low) != len(set(low))
            or low != sorted(low) or low != sorted({value & 0xFFFFFFFF for value in full})):
        raise FreezeError("ancestry low-32 setup-ID list is invalid")
    if hashlib.sha256("".join(f"{value}\n" for value in full).encode()).hexdigest() != source.get("full_setup_ids_sha256_lines"):
        raise FreezeError("ancestry full setup-ID line hash differs")
    if hashlib.sha256("".join(f"{value}\n" for value in low).encode()).hexdigest() != source.get("low32_setup_ids_sha256_lines"):
        raise FreezeError("ancestry low-32 setup-ID line hash differs")
    return set(full), set(low)


def _candidate_ancestry(run: dict, checkpoint: Path) -> tuple[set[int], list[dict]]:
    receipt_path = rooted(ANCESTRY_SETUP_IDS_PATH)
    if sha(receipt_path) != ANCESTRY_SETUP_IDS_SHA256:
        raise FreezeError("candidate ancestry setup-ID receipt differs from its registered hash")
    ancestry = read_json(receipt_path)
    if ancestry.get("schema") != "candidate-ancestry-setup-ids-v1":
        raise FreezeError("candidate ancestry setup-ID receipt schema differs")
    lineage = ancestry.get("candidate_lineage", {})
    for path_value, key in ((lineage.get("current_candidate_checkpoint"), "current_candidate_sha256"),
            (lineage.get("warm_parent_checkpoint"), "warm_parent_sha256"),
            (lineage.get("base_entity_checkpoint_path"), "base_entity_parent_sha256"),
            (lineage.get("baseline_corpus_registry"), "baseline_corpus_registry_sha256")):
        if not path_value or sha(rooted(path_value)) != lineage.get(key):
            raise FreezeError(f"candidate ancestry lineage hash differs: {path_value}")
    if lineage.get("first_onehot_runtime_sha256") != lineage.get("warm_parent_sha256"):
        raise FreezeError("onehot runtime differs from the hash-bound warm parent")
    if checkpoint.is_file():
        selected_sha = sha(checkpoint)
        if selected_sha not in (lineage.get("current_candidate_sha256"),
                lineage.get("warm_parent_sha256")):
            selected_sha_is_child = any(branch.get("status") == "complete"
                and branch.get("parent_sha256") == lineage.get("current_candidate_sha256")
                and branch.get("selected_model_sha256") == selected_sha
                for branch in run.get("training_branches", []))
            if not selected_sha_is_child:
                raise FreezeError("selected checkpoint is not a hash-bound ancestry checkpoint")
    if sha(rooted("local/research/sprint48/ready/first/onehot/model.pt")) != lineage.get("onehot_selected_checkpoint_sha256"):
        raise FreezeError("selected onehot checkpoint differs from the ancestry receipt")
    if sha(rooted("research/training_strategy/first-stage-evidence.json")) != lineage.get("onehot_selection_evidence_sha256"):
        raise FreezeError("onehot selection evidence differs from the ancestry receipt")
    if sha(rooted("research/entity_baseline/freeze.json")) != lineage.get("base_entity_freeze_sha256"):
        raise FreezeError("base entity freeze differs from the ancestry receipt")
    if sha(rooted("local/research/sprint48/refit-01/fit/manifest.json")) != lineage.get("refit_manifest_sha256"):
        raise FreezeError("refit manifest differs from the ancestry receipt")
    archive_binding = ancestry.get("archive_binding", {})
    archive = rooted(archive_binding.get("archive", ""))
    archive_manifest_path = archive / "manifest.json"
    archive_manifest_sha = archive_binding.get("manifest_sha256")
    if (archive_manifest_sha != FIRST_CANDIDATE_ARCHIVE_MANIFEST
            or archive_binding.get("manifest_member_sha256") != archive_manifest_sha
            or sha(archive_manifest_path) != archive_manifest_sha):
        raise FreezeError("candidate ancestry archive manifest differs from its registered hash")
    archive_manifest = read_json(archive_manifest_path)
    ids, source_receipts = set(), []
    all_sources = ancestry.get("extra_ancestor_corpora", []) + ancestry.get("historical_selection_screens", [])
    corpus_names = {source.get("name") for source in ancestry.get("extra_ancestor_corpora", [])}
    for source in all_sources:
        full, low = _listed_ids(source)
        if source.get("name") in corpus_names:
            if (source.get("archive") != archive_binding.get("archive")
                    or source.get("archive_manifest_sha256") != archive_manifest_sha):
                raise FreezeError("ancestry corpus archive binding differs")
            actual, member_receipt = _archive_member_ids(archive, archive_manifest,
                source.get("member", ""), source.get("row_bytes", 0))
            if (actual != full or member_receipt.get("sha256") != source.get("source_sha256")
                    or member_receipt.get("bytes") != source.get("source_bytes")
                    or member_receipt.get("rows") != source.get("rows")):
                raise FreezeError(f"ancestry corpus differs from its archive member: {source.get('name')}")
            source_receipt = {"name": source.get("name"), "source": "archive-member",
                "archive_manifest_sha256": archive_manifest_sha, **member_receipt}
        else:
            if source.get("source_archive"):
                if (source.get("source_archive") != archive_binding.get("archive")
                        or source.get("source_archive_manifest_sha256") != archive_manifest_sha):
                    raise FreezeError("selection screen archive binding differs")
                content, member_receipt = _archive_member_bytes(archive, archive_manifest,
                    source.get("source_member", ""))
                content_sha = hashlib.sha256(content).hexdigest()
                source_receipt = {"name": source.get("name"), "source": "archive-member",
                    "archive_manifest_sha256": archive_manifest_sha, **member_receipt}
            else:
                path = rooted(source.get("source_path", ""))
                if sha(path) != source.get("source_sha256"):
                    raise FreezeError(f"historical selection screen hash differs: {path}")
                content = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
                content_sha = sha(path)
                source_receipt = {"name": source.get("name"), "source": str(path),
                    "source_sha256": content_sha}
            if content_sha != source.get("source_sha256"):
                raise FreezeError(f"historical selection screen content hash differs: {source.get('name')}")
            if source.get("raw_game_records_retained") is False:
                schedule_path = rooted(source.get("schedule_source_path", ""))
                if sha(schedule_path) != source.get("schedule_source_sha256"):
                    raise FreezeError(f"historical schedule generator hash differs: {schedule_path}")
                try:
                    summary = json.loads(content)
                except json.JSONDecodeError as error:
                    raise FreezeError(f"historical confirmation summary is invalid: {source.get('name')}") from error
                if (summary.get("master") != source.get("master")
                        or summary.get("games") != source.get("records")
                        or summary.get("completed") != source.get("records")
                        or summary.get("record_set_sha256") != source.get("raw_record_set_sha256")):
                    raise FreezeError(f"historical confirmation summary differs: {source.get('name')}")
                actual = {setup_seed(source["master"], block)
                    for block in range(source["paired_setup_blocks"])}
                if len(actual) != source.get("unique_full_setup_ids"):
                    raise FreezeError(f"reconstructed historical setup IDs are not unique: {source.get('name')}")
                source_receipt["schedule_source"] = str(schedule_path)
                source_receipt["schedule_source_sha256"] = source["schedule_source_sha256"]
                source_receipt["setup_id_derivation"] = "SHA256 native-v1:{master}:setup:{block}:0; first 8 bytes little-endian"
            else:
                try:
                    value = json.loads(content)
                    records = value.get("records") if isinstance(value, dict) else value
                    actual = {int(row["seed"]) for row in records}
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                    raise FreezeError(f"historical selection screen records are invalid: {source.get('name')}") from error
                if actual != full or len(records) != source.get("records"):
                    raise FreezeError(f"historical selection screen setup IDs differ: {source.get('name')}")
            if actual != full:
                raise FreezeError(f"historical selection screen setup IDs differ: {source.get('name')}")
        ids.update(full)
        source_receipts.append(source_receipt | {"setup_ids": len(full),
            "full_setup_ids_sha256_lines": source["full_setup_ids_sha256_lines"],
            "low32_setup_ids_sha256_lines": source["low32_setup_ids_sha256_lines"]})
    combined = ancestry.get("combined_setup_ids", {})
    combined_full, combined_low = _listed_ids(combined)
    if ids != combined_full or len(ids) != ancestry.get("validation", {}).get("unique_ancestry_full_ids"):
        raise FreezeError("combined candidate ancestry setup IDs differ from source lists")
    existing = ancestry.get("overlap_with_existing_sprint_exclusions", {})
    excluded_path = rooted(existing.get("path", ""))
    if sha(excluded_path) != existing.get("sha256"):
        raise FreezeError("ancestry preflight exclusion file hash differs")
    existing_ids = {int(line) for line in excluded_path.read_text().splitlines() if line.strip()}
    if len(existing_ids) != existing.get("existing_ids") or ids & existing_ids:
        raise FreezeError("candidate ancestry IDs overlap their recorded preflight exclusions")
    source_receipts.insert(0, {"name": "candidate-ancestry-id-receipt",
        "path": str(receipt_path), "sha256": ANCESTRY_SETUP_IDS_SHA256,
        "source_count": len(all_sources), "unique_full_setup_ids": len(ids),
        "unique_low32_setup_ids": len({value & 0xFFFFFFFF for value in ids}),
        "full_setup_ids_sha256_lines": combined["full_setup_ids_sha256_lines"],
        "low32_setup_ids_sha256_lines": combined["low32_setup_ids_sha256_lines"]})
    return ids, source_receipts


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


def _read_setup_id_file(path_value: str | Path, expected_sha256: str,
                        expected_count: int | None = None,
                        base: Path = ROOT) -> tuple[set[int], Path]:
    path_value = Path(path_value)
    path = rooted(path_value if path_value.is_absolute() else base / path_value)
    if sha(path) != expected_sha256:
        raise FreezeError(f"setup-ID file hash differs: {path}")
    try:
        values = [int(line) for line in path.read_text().splitlines() if line.strip()]
    except ValueError as error:
        raise FreezeError(f"setup-ID file has a non-integer value: {path}") from error
    if any(value < 0 or value > 0xFFFFFFFFFFFFFFFF for value in values) or len(values) != len(set(values)):
        raise FreezeError(f"setup-ID file has invalid or duplicate values: {path}")
    if expected_count is not None and len(values) != expected_count:
        raise FreezeError(f"setup-ID count differs: {path}")
    return set(values), path


def _collection_ids(run: dict) -> tuple[set[int], list[dict]]:
    """Audit setup IDs consumed by collection and offline-label jobs."""
    ids, receipts = set(), []
    for field in ("data_collection_jobs", "offline_label_jobs"):
        jobs = run.get(field, [])
        if not isinstance(jobs, list):
            raise FreezeError(f"RUN.json {field} must be a list")
        for job in jobs:
            status = job.get("status")
            if status in ("queued", "running"):
                raise FreezeError(f"cannot freeze while a {field} job is {status}")
            if status not in ("complete", "failed"):
                raise FreezeError(f"cannot audit {field} job with status {status!r}")
            output = rooted(job.get("output", ""))
            run_receipt_path = output / "run.json"
            declared_receipt = job.get("receipt")
            if declared_receipt is not None:
                declared_path = rooted(declared_receipt)
                if declared_path != run_receipt_path:
                    raise FreezeError(f"{field} receipt path differs from its output: {declared_path}")
                if job.get("receipt_sha256") is not None and sha(declared_path) != job["receipt_sha256"]:
                    raise FreezeError(f"{field} receipt hash differs from RUN.json: {declared_path}")
            run_receipt = read_json(run_receipt_path)
            expected_schema = ("sprint48-dagger-source-collection-v1" if field == "data_collection_jobs"
                               else "sprint48-offline-label-run-result-v1")
            if run_receipt.get("schema") != expected_schema:
                raise FreezeError(f"{field} run receipt schema differs: {run_receipt_path}")
            receipt = {"source": field, "output": str(output),
                "run_receipt": str(run_receipt_path), "run_receipt_sha256": sha(run_receipt_path),
                "status": status}
            if field == "data_collection_jobs":
                if run_receipt.get("status") != status:
                    raise FreezeError(f"{field} status differs from its run receipt: {output}")
                sources = run_receipt.get("sources")
                if not isinstance(sources, list) or not sources:
                    raise FreezeError(f"{field} receipt has no source splits: {output}")
                split_receipts = []
                for source in sources:
                    split = source.get("split")
                    if split not in ("train", "dev") or source.get("status") != "complete":
                        raise FreezeError(f"{field} source split is incomplete: {output}")
                    raw = rooted(source.get("raw", ""))
                    if sha(raw) != source.get("raw_sha256"):
                        raise FreezeError(f"{field} raw schedule hash differs: {raw}")
                    master = source.get("source_master")
                    if not isinstance(master, int) or master < 0 or master == MASTER:
                        raise FreezeError(f"{field} source master is invalid: {raw}")
                    raw_ids = set()
                    rows_seen = 0
                    header_seen = False
                    with raw.open() as stream:
                        for line in stream:
                            if not line.strip():
                                continue
                            row = json.loads(line)
                            if not header_seen:
                                header_seen = True
                                if row.get("master") != master:
                                    raise FreezeError(f"{field} raw master differs from its receipt: {raw}")
                                continue
                            seed, block = row.get("setup_seed"), row.get("block")
                            if not isinstance(seed, int) or not isinstance(block, int) or seed != setup_seed(master, block):
                                raise FreezeError(f"{field} raw setup ID differs from master/block: {raw}")
                            raw_ids.add(seed)
                            rows_seen += 1
                    games = source.get("games")
                    if rows_seen != games or not header_seen:
                        raise FreezeError(f"{field} raw row count differs from its receipt: {raw}")
                    ids_path = output / split / "setup_ids.txt"
                    split_ids, ids_path = _read_setup_id_file(ids_path, source.get("setup_ids_sha256", ""),
                        expected_count=source.get("paired_setups"))
                    if split_ids != raw_ids:
                        raise FreezeError(f"{field} setup-ID file differs from raw schedule: {raw}")
                    ids.update(split_ids)
                    split_receipts.append({"split": split, "raw": str(raw), "raw_sha256": sha(raw),
                        "setup_ids_file": str(ids_path), "setup_ids_sha256": sha(ids_path),
                        "setup_ids": len(split_ids), "source_master": master})
                receipt["splits"] = split_receipts
            else:
                if run_receipt.get("status") != status:
                    raise FreezeError(f"{field} status differs from its run receipt: {output}")
                registry_hash = run_receipt.get("registry_sha256")
                if status == "failed" and not registry_hash:
                    plan_path = rooted(run_receipt.get("plan", ""))
                    plan_hash = run_receipt.get("plan_sha256")
                    if not isinstance(plan_hash, str) or sha(plan_path) != plan_hash:
                        raise FreezeError(f"{field} failed-plan hash differs: {plan_path}")
                    plan = read_json(plan_path)
                    if plan.get("schema") != "sprint48-offline-label-run-v1":
                        raise FreezeError(f"{field} failed-plan schema differs: {plan_path}")
                    source = rooted(plan.get("source", ""))
                    if sha(source) != plan.get("source_sha256") or run_receipt.get("source_unchanged") is not True:
                        raise FreezeError(f"{field} failed-plan source is not hash-bound: {source}")
                    master = plan.get("source_master")
                    if not isinstance(master, int) or master < 0 or master == MASTER:
                        raise FreezeError(f"{field} failed-plan source master is invalid: {plan_path}")
                    worker_ids = plan.get("worker_setup_ids")
                    worker_blocks = plan.get("worker_blocks")
                    workers = plan.get("workers")
                    if (not isinstance(workers, int) or workers < 1
                            or not isinstance(worker_ids, dict) or not isinstance(worker_blocks, dict)
                            or set(worker_ids) != {str(i) for i in range(workers)}
                            or set(worker_blocks) != set(worker_ids)):
                        raise FreezeError(f"{field} failed-plan worker assignments are invalid: {plan_path}")
                    assigned_ids, assigned_blocks = [], []
                    for worker in range(workers):
                        raw_ids = worker_ids[str(worker)]
                        blocks = worker_blocks[str(worker)]
                        if (not isinstance(raw_ids, list) or not isinstance(blocks, list)
                                or len(raw_ids) != len(blocks)):
                            raise FreezeError(f"{field} failed-plan worker assignment is invalid: {plan_path}")
                        assigned_ids.extend(raw_ids)
                        assigned_blocks.extend(blocks)
                    if (any(not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF
                            for value in assigned_ids)
                            or len(assigned_ids) != len(set(assigned_ids))
                            or len(assigned_blocks) != len(set(assigned_blocks))
                            or set(assigned_blocks) != set(plan.get("eligible_blocks", []))
                            or len(assigned_ids) != plan.get("eligible_setup_ids")):
                        raise FreezeError(f"{field} failed-plan eligible assignments differ: {plan_path}")
                    block_ids = {}
                    with source.open() as stream:
                        header_seen = False
                        for line in stream:
                            if not line.strip():
                                continue
                            row = json.loads(line)
                            if not header_seen:
                                header_seen = True
                                if row.get("master") != master:
                                    raise FreezeError(f"{field} failed-plan source master differs: {source}")
                                continue
                            block, setup_id = row.get("block"), row.get("setup_seed")
                            if (not isinstance(block, int) or not isinstance(setup_id, int)
                                    or setup_id != setup_seed(master, block)):
                                raise FreezeError(f"{field} failed-plan source setup ID differs: {source}")
                            if block in block_ids and block_ids[block] != setup_id:
                                raise FreezeError(f"{field} failed-plan source block conflicts: {source}")
                            block_ids[block] = setup_id
                    if not header_seen or any(block_ids.get(block) != setup_id
                            for worker in range(workers)
                            for block, setup_id in zip(worker_blocks[str(worker)], worker_ids[str(worker)])):
                        raise FreezeError(f"{field} failed-plan IDs do not match source schedule: {source}")
                    ids.update(assigned_ids)
                    receipt.update(plan=str(plan_path), plan_sha256=plan_hash,
                        plan_source=str(source), plan_source_sha256=plan["source_sha256"],
                        setup_ids=len(set(assigned_ids)), status="failed-plan-audited")
                    receipts.append(receipt)
                    continue
                registry_path = rooted(run_receipt.get("registry", ""))
                if registry_hash != job.get("registry_sha256") or sha(registry_path) != registry_hash:
                    raise FreezeError(f"{field} registry hash differs: {registry_path}")
                registry = read_json(registry_path)
                if registry.get("schema") != "sprint48-offline-label-registry-v1":
                    raise FreezeError(f"{field} registry schema differs: {registry_path}")
                if job.get("split") is not None and registry.get("split") != job["split"]:
                    raise FreezeError(f"{field} split differs from its registry: {registry_path}")
                setup_ids, ids_path = _read_setup_id_file(
                    registry.get("setup_ids_file", ""), registry.get("setup_ids_sha256", ""),
                    expected_count=registry.get("setup_count"), base=registry_path.parent)
                ids.update(setup_ids)
                receipt.update(registry=str(registry_path), registry_sha256=registry_hash,
                    setup_ids_file=str(ids_path), setup_ids_sha256=sha(ids_path),
                    setup_ids=len(setup_ids))
            receipts.append(receipt)
    return ids, receipts


def _control_queue_receipts(run: dict) -> list[dict]:
    """Require registered bounded supervisors to finish before final freeze."""
    jobs = run.get("control_queue_jobs", [])
    if not isinstance(jobs, list):
        raise FreezeError("RUN.json control_queue_jobs must be a list")
    receipts = []
    for job in jobs:
        run_status = job.get("status")
        if run_status not in ("queued", "running", "complete"):
            raise FreezeError(f"cannot audit control_queue_jobs job with status {run_status!r}")
        receipt_value = job.get("receipt")
        receipt_path_value = job.get("receipt_path")
        if receipt_value is None and receipt_path_value is None:
            raise FreezeError("control_queue_jobs entry has no receipt path")
        if (receipt_value is not None and receipt_path_value is not None
                and rooted(receipt_value) != rooted(receipt_path_value)):
            raise FreezeError("control_queue_jobs receipt aliases differ")
        receipt_path = rooted(receipt_value if receipt_value is not None else receipt_path_value)
        if job.get("receipt_sha256") is not None and sha(receipt_path) != job["receipt_sha256"]:
            raise FreezeError(f"control queue receipt hash differs from RUN.json: {receipt_path}")
        receipt = read_json(receipt_path)
        if receipt.get("schema") != "sprint48-trial06-07-supervisor-v1":
            raise FreezeError(f"control_queue_jobs receipt schema differs: {receipt_path}")
        if receipt.get("status") != "complete":
            raise FreezeError(
                f"cannot freeze while control_queue_jobs receipt is {receipt.get('status')!r}")
        source_path_value = receipt.get("source_path")
        source_hash = receipt.get("source_sha256")
        if source_path_value is not None or source_hash is not None:
            if not source_path_value or not isinstance(source_hash, str):
                raise FreezeError(f"control queue source binding is incomplete: {receipt_path}")
            source_path = rooted(source_path_value)
            actual_source_hash = sha(source_path)
            if actual_source_hash != source_hash:
                raise FreezeError(f"control queue source hash differs: {source_path}")
            recorded_source_hash = job.get("source_sha256")
            if recorded_source_hash is not None and recorded_source_hash != source_hash:
                raise FreezeError(f"control queue source hash differs from RUN.json: {source_path}")
        else:
            source_path = None
            actual_source_hash = None
        receipts.append({
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha(receipt_path),
            "status": receipt["status"],
            "run_status": run_status,
            "status_from_receipt": run_status != receipt["status"],
            "source_path": str(source_path) if source_path else None,
            "source_sha256": actual_source_hash,
        })
    return receipts


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
    control_queue_receipts = _control_queue_receipts(run)
    _check_no_final_outcomes(output_root, run)
    train_ids, corpus_receipts = corpus_ids(registries)
    ancestry_ids, ancestry_receipts = _candidate_ancestry(run, Path(candidate["checkpoint"]))
    trial_ids, trial_receipts = explored_ids(run_path)
    collection_setup_ids, collection_receipts = _collection_ids(run)
    final_ids = final_setup_ids(games)
    excluded_ids = train_ids | ancestry_ids | trial_ids | collection_setup_ids
    check_disjoint(final_ids, excluded_ids)

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
            "excluded_low32_sha256": hash_value(sorted({seed & 0xFFFFFFFF for seed in excluded_ids})),
            "excluded_ids": len(excluded_ids), "overlap_count": 0,
            "no_prior_final_outcomes_found": True, "output_root_scanned": str(output_root),
            "corpus_registries": [{"path": str(p), "sha256": sha(p)} for p in registries],
            "corpus_sources": corpus_receipts,
            "model_ancestry_sources": ancestry_receipts,
            "collection_sources": collection_receipts,
            "control_queue_sources": control_queue_receipts,
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
