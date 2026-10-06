#!/usr/bin/env python3
"""Build and check the fixed DAgger source-ID exclusion list."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/strength/native"))
sys.path.insert(0, str(ROOT / "research"))
from upstream import stream  # noqa: E402
from flywheel_model import open_rows  # noqa: E402
from learner_data import check_setup_id_disjoint  # noqa: E402

RUN = ROOT / "research/sprint48/RUN.json"
BASE = ROOT / "local/research/architecture-pivots/expanded-data.json"
PILOT_AND_FULL = ROOT / "local/research/sprint48/dagger-train-pilot-00"
TRIAL00_FULL = ROOT / "local/research/sprint48/dagger-train-trial00-full"
OUTPUT = ROOT / "local/research/sprint48/dagger-branch2-excluded-setup-ids.txt"
TRAIN_MASTER, TRAIN_SETUPS = 17710000000, 512
DEV_MASTER, DEV_SETUPS = 17720000000, 128


def gather() -> tuple[set[int], dict[str, int]]:
    run = json.loads(RUN.read_text())
    registry = json.loads(BASE.read_text())
    _, base_train, _ = open_rows([entry["source"] for entry in registry["train"]])
    _, base_dev, _ = open_rows([entry["source"] for entry in registry["dev"]])
    excluded = set(base_train) | set(base_dev)
    counts = {"expanded_base_train_and_dev": len(excluded)}

    seen_masters: set[int] = set()
    for trial in run["consumed_trials"]:
        master = int(trial["master"])
        if master in seen_masters:
            raise ValueError(f"campaign repeats consumed master {master}")
        seen_masters.add(master)
        if trial.get("status") not in {"complete", "running"}:
            raise ValueError(f"consumed master {master} has invalid status")
        games = int(trial["games"])
        if games <= 0 or games % 2:
            raise ValueError(f"consumed master {master} does not have a complete paired schedule size")
        ids = {stream(master, "setup", block) for block in range(games // 2)}
        excluded.update(ids)
        counts[f"consumed_{master}"] = len(ids)

    pilot_ids_path = PILOT_AND_FULL / "setup_ids.txt"
    full_ids_path = TRIAL00_FULL / "setup_ids.txt"
    for name, ids_path in (("trial00_pilot_labels", pilot_ids_path),
                           ("trial00_full_labels", full_ids_path)):
        if not ids_path.exists():
            raise FileNotFoundError(f"trial-00 setup-ID file is missing: {ids_path}")
        ids = {int(line) for line in ids_path.read_text().splitlines() if line.strip()}
        excluded.update(ids)
        counts[name] = len(ids)

    validation = {int(value) for value in run.get("validation_setup_ids", [])}
    excluded.update(validation)
    counts["validation_full_ids"] = len(validation)
    counts["validation_low32_ids"] = len({value & 0xffffffff for value in validation})
    return excluded, counts


def check_future(excluded: set[int]) -> dict:
    train = [stream(TRAIN_MASTER, "setup", block) for block in range(TRAIN_SETUPS)]
    dev = [stream(DEV_MASTER, "setup", block) for block in range(DEV_SETUPS)]
    check_setup_id_disjoint(train, excluded)
    check_setup_id_disjoint(dev, excluded | set(train))
    train_low = {seed & 0xffffffff for seed in train}
    dev_low = {seed & 0xffffffff for seed in dev}
    if train_low & dev_low:
        raise ValueError("future train and dev schedules overlap after native low-32-bit seeding")
    return dict(train_setups=len(train), dev_setups=len(dev),
                train_exact_overlap=0, dev_exact_overlap=0,
                train_dev_full_overlap=0, train_dev_low32_overlap=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="write the fixed exclusion list")
    action.add_argument("--check", action="store_true", help="check inputs and future IDs without writes")
    args = parser.parse_args()
    excluded, counts = gather()
    future = check_future(excluded)
    if args.prepare:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text("".join(f"{value}\n" for value in sorted(excluded)))
    else:
        if not OUTPUT.is_file():
            raise FileNotFoundError(f"exclusion list is missing: {OUTPUT}; run --prepare first")
        recorded = {int(line) for line in OUTPUT.read_text().splitlines() if line.strip()}
        if recorded != excluded:
            raise ValueError("exclusion list differs from the current source registries and campaign records")
    print(json.dumps(dict(status="prepared" if args.prepare else "checked",
        exclusion_path=str(OUTPUT), exclusion_ids=len(excluded), counts=counts,
        future_ids=future), sort_keys=True))


if __name__ == "__main__":
    main()
