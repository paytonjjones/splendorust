"""Validate and run the finite Sprint 48 learner-state DAgger fit.

This wrapper is prepared for a later authorized run. It never collects games
or labels. It checks the frozen refit-01 parent, the expanded base registry,
the two fresh label registries, split IDs, and the campaign deadline before it
starts the copied trainer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "research/sprint48"))
from flywheel_model import DTYPE, open_rows, sha  # noqa: E402
from learner_data import check_setup_id_disjoint, read_setup_ids  # noqa: E402
from branch2_train import (  # noqa: E402
    BATCH,
    DAGGER_ROWS_PER_UPDATE,
    EPOCHS,
    PARENT_SHA256,
)

RUN_PATH = ROOT / "research/sprint48/RUN.json"
BASE_REGISTRY = ROOT / "local/research/architecture-pivots/expanded-data.json"
BASE_REGISTRY_SHA256 = "4dd2f1a9c8f9e78a192a10da1c686dac3481e76c45a4034a931fae61a4eca581"
PARENT_CHECKPOINT = ROOT / "local/research/sprint48/refit-01/fit/model.pt"
RUNTIME_PYTHON = ROOT / "local/strength/inference/bin/python"
TRAINER = ROOT / "research/sprint48/branch2_train.py"
TRAIN_MASTER = 17710000000
DEV_MASTER = 17720000000
EXPECTED_TRAIN_SETUP_COUNT = 512
EXPECTED_DEV_SETUP_COUNT = 128
TEACHER_REVISION = "32a27ac1f85d5de2766cc5f60c2bf04e557f7836"
TEACHER_CHECKPOINT_SHA256 = "6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def resolve_file(path_value: str, parent: Path) -> Path:
    path = Path(path_value)
    return (path if path.is_absolute() else parent / path).resolve(strict=True)


def validate_base_registry(path: Path) -> tuple[dict, set[int], set[int]]:
    if sha(path) != BASE_REGISTRY_SHA256:
        raise ValueError("expanded base registry SHA256 differs from the frozen source")
    value = json.loads(path.read_text())
    if value.get("setup_counts") != {"train": 30000, "dev": 2000}:
        raise ValueError("expanded base registry must contain 30,000 train and 2,000 dev setups")
    for split in ("train", "dev"):
        entries = value.get(split)
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"expanded base registry has no {split} entries")
        for index, entry in enumerate(entries):
            for field in ("source", "context", "inputs"):
                path_entry = resolve_file(entry[field], path.parent)
                if sha(path_entry) != entry[field + "_sha256"]:
                    raise ValueError(f"expanded base {split} {index} {field} hash differs")
            source = Path(entry["source"])
            if source.stat().st_size != int(entry["rows"]) * DTYPE.itemsize:
                raise ValueError(f"expanded base {split} {index} row size differs")
            packed = Path(entry["inputs"])
            if packed.stat().st_size != int(entry["rows"]) * 525 * 4:
                raise ValueError(f"expanded base {split} input size differs")
    train_rows, train_ids, _ = open_rows([e["source"] for e in value["train"]])
    dev_rows, dev_ids, _ = open_rows([e["source"] for e in value["dev"]])
    if train_ids & dev_ids:
        raise ValueError("expanded base train and dev setup IDs overlap")
    if sum(map(len, train_rows)) != 1682022:
        raise ValueError("expanded base row count differs from refit-01")
    if sum(map(len, dev_rows)) <= 0:
        raise ValueError("expanded base dev is empty")
    return value, train_ids, dev_ids


def validate_collector_receipt(source_root: Path) -> dict:
    receipt_path = source_root / "run.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "complete":
        raise ValueError("branch-two source collector did not complete")
    if receipt.get("checkpoint_sha256") != PARENT_SHA256:
        raise ValueError("source schedules do not come from frozen refit-01")
    if receipt.get("search") != dict(iterations=128, depth=16, world_pool=3,
                                      search="gumbel", gumbel_max_considered=16,
                                      chance_universes=0, root_only=False, dynamic_fpu=False):
        raise ValueError("source collector search settings differ")
    if receipt.get("masters") != dict(train=TRAIN_MASTER, dev=DEV_MASTER):
        raise ValueError("source collector masters differ")
    if receipt.get("sizes") != dict(train_games=1024, train_setups=512,
                                     dev_games=256, dev_setups=128):
        raise ValueError("source collector schedule sizes differ")
    source_runs = receipt.get("sources", [])
    if len(source_runs) != 2 or {(item.get("split"), item.get("source_master"), item.get("games"), item.get("status"))
        for item in source_runs} != {
            ("train", TRAIN_MASTER, 1024, "complete"),
            ("dev", DEV_MASTER, 256, "complete")
        }:
        raise ValueError("source collector train and dev receipts are incomplete")
    descriptor = receipt.get("descriptor", {})
    descriptor_path = Path(descriptor.get("path", ""))
    if not descriptor_path.is_file() or sha(descriptor_path) != descriptor.get("sha256"):
        raise ValueError("frozen runtime descriptor is missing or changed")
    for relative, expected in receipt.get("source_hashes", {}).items():
        frozen = source_root / "sources" / relative
        if not frozen.is_file() or sha(frozen) != expected:
            raise ValueError(f"frozen source copy is missing or changed: {relative}")
    provenance = receipt.get("compiled_binary_provenance", {})
    if provenance.get("source_schedule_source_sha256") is None:
        raise ValueError("frozen binary build provenance is missing")
    for relative, expected in provenance.get("compiled_source_hashes", {}).items():
        frozen = source_root / "compiled-source" / relative
        if not frozen.is_file() or sha(frozen) != expected:
            raise ValueError(f"compiled source provenance is missing or changed: {relative}")
    binaries = receipt.get("binaries", {})
    if binaries.get("native_policy_worker", {}).get("sha256") != \
            "424d3788f936542a0080750ed8445c9d9d2960328a6b87830da4b3e032b6d3b1" or \
            binaries.get("strength_worker", {}).get("sha256") != \
            "6e90d2d1741a34d3323247833ff426b821ccaeefce683a25b34d9ff04ca306e7":
        raise ValueError("source collection uses executables outside the frozen build-controls build")
    return receipt


def validate_label_registry(path: Path, split: str, source_master: int,
                            expected_setups: int, collector: dict) -> tuple[dict, list[dict], set[int], set[int]]:
    registry = json.loads(path.read_text())
    if registry.get("schema") != "sprint48-offline-label-registry-v1":
        raise ValueError(f"wrong {split} DAgger registry schema")
    if registry.get("split") != split or registry.get("setup_count") != expected_setups:
        raise ValueError(f"{split} DAgger setup count or split differs")
    if registry.get("learner_descriptor_sha256") != collector["descriptor"]["sha256"]:
        raise ValueError(f"{split} labels use another learner descriptor")
    ids_file = resolve_file(registry["setup_ids_file"], path.parent)
    low32_file = resolve_file(registry["low32_setup_ids_file"], path.parent)
    if sha(ids_file) != registry["setup_ids_sha256"] or sha(low32_file) != registry["low32_setup_ids_sha256"]:
        raise ValueError(f"{split} setup-ID list hash differs")
    full_ids = read_setup_ids(ids_file)
    low32_ids = read_setup_ids(low32_file)
    if len(full_ids) != expected_setups or len(low32_ids) != expected_setups:
        raise ValueError(f"{split} setup-ID list count differs")
    if low32_ids != {value & 0xffffffff for value in full_ids}:
        raise ValueError(f"{split} low-32-bit setup IDs do not match full IDs")
    manifests = registry.get("worker_manifests", [])
    if len(manifests) != 8:
        raise ValueError(f"{split} DAgger labels must have eight worker manifests")
    entries = registry.get("entries", [])
    if len(entries) != 8 or sum(int(entry["rows"]) for entry in entries) != int(registry["rows"]):
        raise ValueError(f"{split} DAgger registry entries differ from the merged row count")
    schedule_meta = None
    worker_setup_ids: set[int] = set()
    binary_hashes: set[tuple[str, str]] = set()
    complete_blocks = incomplete_blocks = 0
    seen_workers: set[int] = set()
    for item in manifests:
        manifest_path = Path(item["path"]).resolve(strict=True)
        if sha(manifest_path) != item["sha256"]:
            raise ValueError(f"{split} worker manifest hash differs")
        manifest = json.loads(manifest_path.read_text())
        worker_id = int(manifest.get("worker_index", -1))
        if worker_id in seen_workers or not 0 <= worker_id < 8:
            raise ValueError(f"{split} worker indices repeat or are out of range")
        seen_workers.add(worker_id)
        if manifest.get("split") != split or int(manifest.get("input_master", -1)) != source_master:
            raise ValueError(f"{split} worker manifest has a wrong split or source master")
        if manifest.get("learner_descriptor_sha256") != collector["descriptor"]["sha256"]:
            raise ValueError(f"{split} worker uses a different descriptor")
        if manifest.get("source_profile") != "alphazero-native-32a27ac-v1":
            raise ValueError(f"{split} worker uses a different AlphaZero profile")
        if manifest.get("teacher_revision") != TEACHER_REVISION or manifest.get("teacher_checkpoint_sha256") != TEACHER_CHECKPOINT_SHA256:
            raise ValueError(f"{split} worker uses a different AlphaZero teacher")
        if manifest.get("teacher_config", {}).get("numMCTSSims") != 800:
            raise ValueError(f"{split} teacher is not AlphaZero800")
        expected_teacher = dict(numMCTSSims=800, fpu=0.0593, universes=3,
            cpuct=0.8, prob_fullMCTS=1.0, forced_playouts=False, no_mem_optim=False)
        if manifest.get("teacher_config") != expected_teacher:
            raise ValueError(f"{split} teacher settings differ from the pinned profile")
        expected_teacher_master, expected_feature_master = (
            (17711000011, 17711000012) if split == "train" else
            (17721000001, 17721000002))
        if manifest.get("teacher_master") != expected_teacher_master or \
                manifest.get("feature_master") != expected_feature_master:
            raise ValueError(f"{split} teacher or feature master differs")
        complete_blocks += int(manifest.get("complete_blocks", 0))
        incomplete_blocks += int(manifest.get("incomplete_blocks", 0))
        if manifest.get("games") != 2 * manifest.get("complete_blocks", 0):
            raise ValueError(f"{split} worker did not label both setup rotations")
        if manifest.get("source_evidence", {}).get("evidence_rejections"):
            raise ValueError(f"{split} source schedule failed evidence checks")
        candidate_search = manifest.get("source_candidate_search", {})
        if candidate_search.get("iterations") != 128 or candidate_search.get("depth") != 16 or \
                candidate_search.get("world_pool") != 3 or candidate_search.get("search") != "gumbel" or \
                candidate_search.get("gumbel_config", {}).get("max_considered") != 16:
            raise ValueError(f"{split} source candidate search settings differ")
        raw_path = Path(manifest["input"]).resolve(strict=True)
        if sha(raw_path) != manifest["input_sha256"]:
            raise ValueError(f"{split} source schedule changed")
        expected_source = next(item for item in collector["sources"] if item["split"] == split)
        if raw_path != Path(expected_source["raw"]).resolve(strict=True) or \
                manifest["input_sha256"] != expected_source["raw_sha256"]:
            raise ValueError(f"{split} labels do not use the frozen collector schedule")
        with raw_path.open() as source:
            metadata = json.loads(source.readline())
        if metadata.get("master") != source_master or metadata.get("model_sha256") != collector["descriptor"]["sha256"]:
            raise ValueError(f"{split} source schedule metadata differs")
        if metadata.get("games") != (1024 if split == "train" else 256) or \
                metadata.get("iterations") != 128 or metadata.get("depth") != 16 or \
                metadata.get("world_pool") != 3 or metadata.get("search") != "gumbel" or \
                metadata.get("gumbel_max_considered") != 16 or metadata.get("root_only") is not False:
            raise ValueError(f"{split} source schedule profile differs")
        if schedule_meta is None:
            schedule_meta = metadata
        elif metadata.get("source_sha256") != schedule_meta.get("source_sha256") or metadata.get("master") != schedule_meta.get("master"):
            raise ValueError(f"{split} worker source schedules differ")
        binary_hashes.add((manifest["policy_binary_sha256"], manifest["strength_binary_sha256"]))
        worker_ids_file = resolve_file(manifest["setup_ids_file"], manifest_path.parent)
        worker_setup_ids |= read_setup_ids(worker_ids_file)
    if complete_blocks != expected_setups or incomplete_blocks != 0:
        raise ValueError(f"{split} worker manifests do not cover every setup exactly once")
    if len(binary_hashes) != 1:
        raise ValueError(f"{split} labels do not use one frozen binary pair")
    if entries and not all(entry.get("native") is True for entry in entries):
        raise ValueError(f"{split} DAgger data must be native only")
    for entry in entries:
        for field in ("source", "context", "inputs"):
            path_entry = Path(entry[field]).resolve(strict=True)
            if sha(path_entry) != entry[field + "_sha256"]:
                raise ValueError(f"{split} DAgger {field} hash differs")
    collector_binaries = collector.get("binaries", {})
    expected_pair = (collector_binaries.get("native_policy_worker", {}).get("sha256"),
                     collector_binaries.get("strength_worker", {}).get("sha256"))
    if binary_hashes != {expected_pair}:
        raise ValueError(f"{split} labels use binaries outside the frozen source collector")
    if worker_setup_ids != full_ids:
        raise ValueError(f"{split} worker setup IDs differ from the merged registry")
    return registry, entries, full_ids, low32_ids


def make_branch_registry(base: dict, train_entries: list[dict], dev_entries: list[dict],
                         sources: dict) -> dict:
    return dict(schema="sprint48-dagger-branch2-registry-v1",
        groups=dict(base_train=base["train"], base_dev=base["dev"],
                    dagger_train=train_entries, dagger_dev=dev_entries),
        source_registries=sources,
        row_counts=dict(base_train=sum(int(e["rows"]) for e in base["train"]),
            base_dev=sum(int(e["rows"]) for e in base["dev"]),
            dagger_train=sum(int(e["rows"]) for e in train_entries),
            dagger_dev=sum(int(e["rows"]) for e in dev_entries)),
        setup_counts=dict(base_train=30000, base_dev=2000,
                          dagger_train=EXPECTED_TRAIN_SETUP_COUNT,
                          dagger_dev=EXPECTED_DEV_SETUP_COUNT))


def campaign_state(*, allow_active_trial: bool = False) -> tuple[dict, dt.datetime]:
    value = json.loads(RUN_PATH.read_text())
    if value.get("status") != "active" or value.get("final_seed_sealed") is not True:
        raise ValueError("Sprint campaign must be active and final seeds must remain sealed")
    deadline = dt.datetime.fromisoformat(value["deadline_utc"].replace("Z", "+00:00"))
    if dt.datetime.now(dt.timezone.utc) >= deadline:
        raise ValueError("Sprint campaign deadline has passed")
    if not allow_active_trial and any(item.get("status") == "running" for item in value.get("consumed_trials", [])):
        raise ValueError("stop and receipt the active external trial before fitting")
    if any(item.get("status") == "running" for item in value.get("training_branches", [])):
        raise ValueError("another training branch is active")
    maximum = json.loads((ROOT / "research/sprint48/PLAN.json").read_text())["maximum_new_training_branches"]
    if len(value.get("training_branches", [])) >= maximum:
        raise ValueError("new training branch allowance is exhausted")
    return value, deadline


def validate_inputs(base_path: Path, train_path: Path, dev_path: Path,
                    parent: Path) -> tuple[dict, dict, dict, dict, dict]:
    if sha(parent) != PARENT_SHA256:
        raise ValueError("parent is not the frozen refit-01 selected checkpoint")
    base, base_train_ids, base_dev_ids = validate_base_registry(base_path)
    if base_train_ids & base_dev_ids:
        raise ValueError("base train and dev setup IDs overlap")
    train_registry_value = json.loads(train_path.read_text())
    first_manifest_path = Path(train_registry_value["worker_manifests"][0]["path"]).resolve(strict=True)
    source_input = Path(json.loads(first_manifest_path.read_text())["input"]).resolve(strict=True)
    source_root = source_input.parent.parent.parent
    collector = validate_collector_receipt(source_root)
    train_registry, train_entries, train_ids, train_low = validate_label_registry(
        train_path, "train", TRAIN_MASTER, EXPECTED_TRAIN_SETUP_COUNT, collector)
    dev_registry, dev_entries, dev_ids, dev_low = validate_label_registry(
        dev_path, "dev", DEV_MASTER, EXPECTED_DEV_SETUP_COUNT, collector)
    if train_registry["learner_descriptor_sha256"] != dev_registry["learner_descriptor_sha256"]:
        raise ValueError("train and dev use different learner descriptors")
    check_setup_id_disjoint(train_ids, base_train_ids | base_dev_ids)
    check_setup_id_disjoint(dev_ids, base_train_ids | base_dev_ids | train_ids)
    if train_low & dev_low:
        raise ValueError("DAgger train and dev low-32-bit IDs overlap")
    base_records = dict(train=base_train_ids, dev=base_dev_ids)
    collector_summary = {key: collector[key] for key in
        ("status", "checkpoint_sha256", "descriptor", "search", "masters", "sizes", "binaries")}
    source_info = dict(collector=collector_summary, collector_path=str(source_root / "run.json"),
        collector_sha256=sha(source_root / "run.json"),
        train_registry_path=str(train_path), train_registry_sha256=sha(train_path),
        dev_registry_path=str(dev_path), dev_registry_sha256=sha(dev_path),
        descriptor_sha256=train_registry["learner_descriptor_sha256"],
        train_setup_ids_sha256=train_registry["setup_ids_sha256"],
        dev_setup_ids_sha256=dev_registry["setup_ids_sha256"])
    return base, train_registry, dev_registry, make_branch_registry(base, train_entries,
        dev_entries, source_info), dict(base=base_records, train_ids=train_ids,
        dev_ids=dev_ids, train_low=train_low, dev_low=dev_low)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger-train-registry", type=Path, required=True)
    parser.add_argument("--dagger-dev-registry", type=Path, required=True)
    parser.add_argument("--base-registry", type=Path, default=BASE_REGISTRY)
    parser.add_argument("--parent", type=Path, default=PARENT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=ROOT / "local/research/sprint48/dagger-branch2-fit")
    parser.add_argument("--python", type=Path, default=RUNTIME_PYTHON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base_path = args.base_registry.resolve(strict=True)
    train_path = args.dagger_train_registry.resolve(strict=True)
    dev_path = args.dagger_dev_registry.resolve(strict=True)
    parent = args.parent.resolve(strict=True)
    runtime_python = Path(os.path.abspath(args.python))
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    if not runtime_python.is_file():
        raise FileNotFoundError(f"missing Python runtime: {runtime_python}")
    if sha(base_path) != BASE_REGISTRY_SHA256:
        raise ValueError("base registry differs from the frozen expanded corpus")
    # A dry run is read-only. It can validate the inputs while a search control
    # uses the GPU; real fitting still requires every external trial to stop.
    _, deadline = campaign_state(allow_active_trial=args.dry_run)
    base, train_registry, dev_registry, branch_registry, ids = validate_inputs(
        base_path, train_path, dev_path, parent)
    if train_registry["setup_count"] != EXPECTED_TRAIN_SETUP_COUNT or \
            dev_registry["setup_count"] != EXPECTED_DEV_SETUP_COUNT:
        raise ValueError("branch two requires 512 train and 128 dev paired setups")
    command = [str(runtime_python), str(TRAINER), "--registry", str(output / "branch-registry.json"),
        "--parent", str(output / "parent.pt"), "--output", str(output / "fit"),
        "--epochs", str(EPOCHS), "--batch", str(BATCH),
        "--dagger-rows", str(DAGGER_ROWS_PER_UPDATE), "--device", "mps"]
    code_paths = [Path(__file__), TRAINER, ROOT / "research/architecture_pivots/models.py",
                  ROOT / "research/flywheel_model.py", ROOT / "research/e95/public_model.py"]
    code_hashes = {str(path.relative_to(ROOT)): sha(path) for path in code_paths}
    copied_registries = dict(base=base_path, dagger_train=train_path, dagger_dev=dev_path)
    plan = dict(schema="sprint48-dagger-branch2-fit-run-v1", status="prepared",
        parent=str(parent), parent_sha256=sha(parent), deadline_utc=deadline.isoformat(),
        source_registries={name: dict(path=str(path), sha256=sha(path))
                           for name, path in copied_registries.items()},
        registry=branch_registry, registry_sha256=None, command=command,
        code_sha256=code_hashes,
        data_counts=dict(base_train_rows=sum(e["rows"] for e in base["train"]),
            base_dev_rows=sum(e["rows"] for e in base["dev"]),
            dagger_train_rows=train_registry["rows"], dagger_dev_rows=dev_registry["rows"],
            dagger_train_setups=len(ids["train_ids"]), dagger_dev_setups=len(ids["dev_ids"])),
        setup_id_checks=dict(base_train=30000, base_dev=2000,
            dagger_train=len(ids["train_ids"]), dagger_dev=len(ids["dev_ids"]),
            exact_overlap=0, native_low32_overlap=0),
        fit=dict(epochs=EPOCHS, batch=BATCH, dagger_rows_per_update=DAGGER_ROWS_PER_UPDATE,
            loss_weights=dict(base=0.90, dagger=0.10), optimizer="fresh AdamW",
            learning_rate=1e-4, weight_decay=1e-4, seed=800000031,
            dagger_seed=0xDA66E2, device="mps", scheduler="cosine, two epochs",
            selection="0.90 * full dev CE+4Brier + 0.10 * DAgger dev CE+4Brier; epoch zero eligible"))
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0

    run, current_deadline = campaign_state()
    if current_deadline != deadline:
        raise ValueError("campaign deadline changed during preflight")
    output.mkdir(parents=True, exist_ok=False)
    inputs_dir = output / "inputs"
    inputs_dir.mkdir()
    for name, path in copied_registries.items():
        shutil.copyfile(path, inputs_dir / f"{name}.json")
        if sha(inputs_dir / f"{name}.json") != sha(path):
            raise ValueError(f"input registry copy failed: {name}")
    shutil.copyfile(parent, output / "parent.pt")
    if sha(output / "parent.pt") != PARENT_SHA256:
        raise ValueError("parent checkpoint copy failed")
    branch_registry["source_registries"] = plan["source_registries"]
    branch_registry_path = output / "branch-registry.json"
    write_json(branch_registry_path, branch_registry)
    plan["registry_sha256"] = sha(branch_registry_path)
    plan_path = output / "plan.json"
    write_json(plan_path, plan)
    receipt = dict(schema="sprint48-dagger-branch2-fit-run-v1", status="starting",
        branch="sprint48-dagger-branch2", branch_index=2,
        started_utc=utc_now(), deadline_utc=deadline.isoformat(),
        driver_pid=os.getpid(), trainer_pid=None, trainer_pgid=None,
        parent=str(output / "parent.pt"), parent_sha256=sha(output / "parent.pt"),
        registry=str(branch_registry_path), registry_sha256=sha(branch_registry_path),
        plan=str(plan_path), plan_sha256=sha(plan_path), command=command,
        cwd=str(ROOT), source_registries=plan["source_registries"],
        code_sha256=code_hashes, data_counts=plan["data_counts"],
        setup_id_checks=plan["setup_id_checks"], fit=plan["fit"],
        receipt_output=str(output), trainer_output=str(output / "fit"))
    write_json(output / "run.json", receipt)
    process = None
    try:
        with (output / "trainer.log").open("wb") as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        receipt.update(status="running", trainer_pid=process.pid, trainer_pgid=process.pid,
                       trainer_started_utc=utc_now())
        write_json(output / "process.json", dict(pid=process.pid, pgid=process.pid,
            command=command, started_utc=receipt["trainer_started_utc"], cwd=str(ROOT)))
        write_json(output / "run.json", receipt)
        expired = False
        while process.poll() is None:
            if dt.datetime.now(dt.timezone.utc) >= deadline:
                expired = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                break
            time.sleep(0.5)
        returncode = process.wait()
        fit_manifest_path = output / "fit/manifest.json"
        fit_manifest = json.loads(fit_manifest_path.read_text()) if fit_manifest_path.is_file() else None
        complete = returncode == 0 and fit_manifest and fit_manifest.get("status") == "complete" and \
            len(fit_manifest.get("history", [])) == EPOCHS
        receipt.update(finished_utc=utc_now(), returncode=returncode,
            last_complete_epoch=len(fit_manifest.get("history", [])) if fit_manifest else 0,
            selected_model_sha256=sha(output / "fit/model.pt") if (output / "fit/model.pt").is_file() else None,
            latest_sha256=sha(output / "fit/latest.pt") if (output / "fit/latest.pt").is_file() else None,
            trainer_manifest_sha256=sha(fit_manifest_path) if fit_manifest_path.is_file() else None,
            status="deadline_stopped" if expired else ("complete" if complete else "failed"))
        write_json(output / "exit.json", dict(returncode=returncode,
            finished_utc=receipt["finished_utc"], deadline_stopped=expired,
            last_complete_epoch=receipt["last_complete_epoch"]))
        if not complete:
            write_json(output / "failure.json", dict(status=receipt["status"],
                returncode=returncode, last_complete_epoch=receipt["last_complete_epoch"],
                note="Keep checkpoints and logs; do not resume in place."))
        write_json(output / "run.json", receipt)
        return 0 if complete else 1
    except BaseException as error:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
        receipt.update(status="failed", finished_utc=utc_now(),
                       error=f"{type(error).__name__}: {error}")
        write_json(output / "failure.json", dict(status="failed", error=receipt["error"]))
        write_json(output / "run.json", receipt)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
