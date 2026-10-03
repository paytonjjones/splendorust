"""Run finite, sharded AlphaZero relabeling on an existing native schedule.

This script does not create games. It validates one complete source schedule,
assigns each eligible paired setup to one worker, starts learner_data.py, and
checks the merged shard manifests and setup IDs before it writes registry
entries. It retains commands, PIDs, logs, hashes, and worker failures.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/sprint48"))
sys.path.insert(0, str(ROOT / "benchmarks/strength/native"))
from evidence import summarize as summarize_evidence  # noqa: E402
from learner_data import (  # noqa: E402
    DEFAULT_POLICY_BINARY,
    DTYPE,
    FINAL_EXTERNAL_MASTER,
    check_setup_id_disjoint,
    paired_blocks,
    read_schedule,
    read_setup_ids,
    validate_schedule,
)
from upstream import DEFAULT_STRENGTH_BINARY, sha  # noqa: E402

DEFAULT_PILOT = ROOT / "local/research/sprint48/dagger-train-pilot-00/manifest.json"
SEED_PLAN = json.loads((ROOT / "research/sprint48/PLAN.json").read_text())["seeds"]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def manifest_setup_ids(path: Path) -> set[int]:
    value = json.loads(path.read_text())
    ids_path = value.get("setup_ids_file")
    if ids_path:
        resolved = Path(ids_path)
        if not resolved.is_absolute():
            resolved = path.parent / resolved
        return read_setup_ids(resolved)
    setup_ids = value.get("setup_ids")
    if setup_ids is None:
        raise ValueError(f"manifest has no setup ID list: {path}")
    return {int(x) for x in setup_ids}


def source_blocks(metadata: dict, records: list[dict], max_blocks: int) -> list[tuple[int, list[dict]]]:
    all_blocks = paired_blocks(records, max_blocks)
    if len(all_blocks) != max_blocks:
        raise ValueError(f"requested {max_blocks} blocks, source has {len(all_blocks)}")
    for block, pair in all_blocks:
        if any(row.get("status") != "complete" for row in pair):
            raise ValueError(f"source block {block} is not two complete games")
    return all_blocks


def assign_blocks(blocks: list[tuple[int, list[dict]]], workers: int,
                  skip_ids: set[int]) -> dict[int, list[int]]:
    assignments = {worker: [block for block, pair in blocks
                            if block % workers == worker
                            and int(pair[0]["setup_seed"]) not in skip_ids]
                   for worker in range(workers)}
    if any(not values for values in assignments.values()):
        raise ValueError("every worker must receive at least one eligible setup block")
    flattened = [block for values in assignments.values() for block in values]
    expected = [block for block, pair in blocks if int(pair[0]["setup_seed"]) not in skip_ids]
    counts = collections.Counter(flattened)
    if sorted(flattened) != sorted(expected) or any(count != 1 for count in counts.values()):
        raise AssertionError("worker assignment does not cover each eligible block exactly once")
    return assignments


def validate_split_master(split: str, master: int) -> None:
    if split != "dev":
        return
    allocation = SEED_PLAN["new_development"]
    start = allocation["master_base"]
    end = start + allocation["master_step"]
    if not start <= master < end:
        raise ValueError("dev labels require a source master from the reserved new-development range")


def build_plan(args: argparse.Namespace) -> tuple[dict, dict, list[tuple[int, list[dict]]], set[int], set[int], Path]:
    source = args.input.resolve(strict=True)
    descriptor = args.learner_descriptor.resolve(strict=True)
    policy_binary = args.policy_binary.resolve(strict=True)
    strength_binary = args.strength_binary.resolve(strict=True)
    exclusion_source = args.exclude_setup_ids.resolve(strict=True)
    args.output = args.output.resolve()
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")

    metadata, records = read_schedule(source)
    validate_schedule(metadata, records, descriptor)
    summary = summarize_evidence(metadata, records)
    if summary["evidence_rejections"]:
        raise ValueError(f"source schedule fails evidence rules: {summary['evidence_rejections']}")
    blocks = source_blocks(metadata, records, args.max_blocks)
    if metadata.get("master") == FINAL_EXTERNAL_MASTER:
        raise ValueError("final external master is sealed")
    validate_split_master(args.split, int(metadata["master"]))
    if len({metadata["master"], args.teacher_master, args.feature_master}) != 3:
        raise ValueError("source, teacher, and feature masters must differ")

    pilot_path = args.pilot_manifest.resolve(strict=True)
    pilot = json.loads(pilot_path.read_text())
    source_hash = sha(source)
    skip_ids = set()
    pilot_ids = manifest_setup_ids(pilot_path)
    if pilot.get("input_sha256") == source_hash:
        if pilot.get("learner_descriptor_sha256") != sha(descriptor):
            raise ValueError("pilot used another descriptor for this source schedule")
        skip_ids |= pilot_ids

    excluded = read_setup_ids(exclusion_source)
    excluded |= pilot_ids
    for previous in args.prior_manifest:
        prior_path = previous.resolve(strict=True)
        excluded |= manifest_setup_ids(prior_path)
    excluded |= skip_ids

    selected_ids = [int(pair[0]["setup_seed"]) for _, pair in blocks
                    if int(pair[0]["setup_seed"]) not in skip_ids]
    if not selected_ids:
        raise ValueError("all source setup blocks were skipped")
    check_setup_id_disjoint(selected_ids, excluded)
    if args.workers > len(selected_ids):
        raise ValueError("workers cannot exceed eligible setup blocks")
    by_worker = assign_blocks(blocks, args.workers, skip_ids)
    expected_blocks = [block for block, pair in blocks
                       if int(pair[0]["setup_seed"]) not in skip_ids]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=False, exist_ok=False)
    combined_exclusions = args.output / "combined-excluded-setup-ids.txt"
    combined_exclusions.write_text("".join(f"{value}\n" for value in sorted(excluded)))
    skip_file = args.output / "skip-setup-ids.txt"
    skip_file.write_text("".join(f"{value}\n" for value in sorted(skip_ids)))

    plan = dict(schema="sprint48-offline-label-run-v1", created_utc=utc_now(),
        source=str(source), source_sha256=source_hash, source_master=metadata["master"],
        source_candidate_sha256=metadata["model_sha256"],
        learner_descriptor=str(descriptor), learner_descriptor_sha256=sha(descriptor),
        policy_binary=str(policy_binary), policy_binary_sha256=sha(policy_binary),
        strength_binary=str(strength_binary), strength_binary_sha256=sha(strength_binary),
        split=args.split, max_blocks=args.max_blocks, workers=args.workers,
        timeout_seconds=args.timeout_seconds,
        teacher_master=args.teacher_master, feature_master=args.feature_master,
        teacher_revision=metadata["upstream_revision"],
        teacher_checkpoint_sha256=metadata["upstream_checkpoint_sha256"],
        teacher_simulations=metadata["external_config"]["numMCTSSims"],
        source_evidence=summary, source_blocks_considered=len(blocks),
        skipped_setup_ids=sorted(skip_ids), eligible_setup_ids=len(expected_blocks),
        eligible_blocks=expected_blocks,
        worker_blocks={str(k): v for k, v in by_worker.items()},
        worker_setup_ids={str(k): [int(pair[0]["setup_seed"]) for block, pair in blocks
                                   if block in set(v) and int(pair[0]["setup_seed"]) not in skip_ids]
                          for k, v in by_worker.items()},
        exclusion_source=str(exclusion_source), exclusion_source_sha256=sha(exclusion_source),
        combined_exclusion_file=str(combined_exclusions),
        combined_exclusion_sha256=sha(combined_exclusions), skip_file=str(skip_file),
        prior_manifests=[dict(path=str(p.resolve(strict=True)), sha256=sha(p.resolve(strict=True)))
                         for p in args.prior_manifest],
        pilot_manifest=str(pilot_path), pilot_manifest_sha256=sha(pilot_path),
        pilot_skipped_because_same_source=bool(skip_ids),
        prior_manifest_hashes=[dict(path=str(p.resolve(strict=True)), sha256=sha(p.resolve(strict=True)))
                               for p in args.prior_manifest],
        immutable_files={str(path): sha(path) for path in
                         [source, descriptor, policy_binary, strength_binary,
                          exclusion_source, pilot_path, combined_exclusions, skip_file,
                          Path(__file__), Path(__file__).with_name("learner_data.py")] +
                         [p.resolve(strict=True) for p in args.prior_manifest]},
        learner_data_sha256=sha(Path(__file__).with_name("learner_data.py")),
        scheduler_sha256=sha(Path(__file__)))
    return plan, metadata, blocks, skip_ids, excluded, combined_exclusions


def commands_for(args: argparse.Namespace, plan: dict, skip_file: Path,
                 combined_exclusions: Path) -> list[list[str]]:
    script = Path(__file__).with_name("learner_data.py").resolve()
    commands = []
    for worker in range(args.workers):
        shard = args.output / f"shard-{worker:02d}"
        command = [sys.executable, str(script),
            "--input", plan["source"],
            "--learner-descriptor", plan["learner_descriptor"],
            "--policy-binary", plan["policy_binary"],
            "--strength-binary", plan["strength_binary"],
            "--output", str(shard), "--split", args.split,
            "--max-blocks", str(args.max_blocks),
            "--workers", str(args.workers), "--worker-index", str(worker),
            "--teacher-master", str(args.teacher_master),
            "--feature-master", str(args.feature_master),
            "--exclude-setup-ids", str(combined_exclusions)]
        if skip_file.stat().st_size:
            command.extend(["--skip-setup-ids", str(skip_file)])
        if args.invariance_checks:
            command.extend(["--invariance-checks", str(args.invariance_checks)])
        else:
            command.extend(["--invariance-checks", "0"])
        commands.append(command)
    return commands


def verify_shards(args: argparse.Namespace, plan: dict, commands: list[list[str]],
                  workers: list[dict], excluded: set[int]) -> dict:
    expected_by_worker = {int(k): v for k, v in plan["worker_blocks"].items()}
    entries, shard_ids, manifests, total_rows = [], [], [], 0
    for worker, result in enumerate(workers):
        if result["exit_code"] != 0:
            continue
        shard = args.output / f"shard-{worker:02d}"
        manifest_path = shard / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest["input_sha256"] != plan["source_sha256"]:
            raise ValueError(f"worker {worker} used a different source schedule")
        if manifest["learner_descriptor_sha256"] != plan["learner_descriptor_sha256"]:
            raise ValueError(f"worker {worker} used a different learner descriptor")
        if manifest["policy_binary_sha256"] != plan["policy_binary_sha256"]:
            raise ValueError(f"worker {worker} used a different policy binary")
        if manifest["strength_binary_sha256"] != plan["strength_binary_sha256"]:
            raise ValueError(f"worker {worker} used a different strength binary")
        if manifest["split"] != args.split or manifest["selected_blocks"] != expected_by_worker[worker]:
            raise ValueError(f"worker {worker} manifest has a wrong split or block assignment")
        if manifest["incomplete_blocks"] != 0 or manifest["complete_blocks"] != len(expected_by_worker[worker]):
            raise ValueError(f"worker {worker} did not label every assigned complete block")
        if manifest["skipped_setup_ids"] != plan["skipped_setup_ids"]:
            raise ValueError(f"worker {worker} did not apply the common pilot skip set")
        ids_path = shard / "setup_ids.txt"
        ids = read_setup_ids(ids_path)
        if len(ids) != manifest["unique_setup_ids"]:
            raise ValueError(f"worker {worker} setup-ID file count differs")
        expected_ids = {int(x) for x in plan["worker_setup_ids"][str(worker)]}
        if ids != expected_ids:
            raise ValueError(f"worker {worker} setup IDs do not match assigned source blocks")
        registry_entry = manifest["registry_entry"]
        if registry_entry["source_sha256"] != manifest["files"]["data.bin"]:
            raise ValueError(f"worker {worker} registry source hash differs")
        if registry_entry["context_sha256"] != manifest["files"]["data.context.bin"]:
            raise ValueError(f"worker {worker} registry context hash differs")
        if registry_entry["inputs_sha256"] != manifest["files"]["data.inputs.bin"]:
            raise ValueError(f"worker {worker} registry input hash differs")
        expected_sizes = {"data.bin": manifest["rows"] * DTYPE.itemsize,
                          "data.context.bin": manifest["rows"] * 7 * 4,
                          "data.inputs.bin": manifest["rows"] * 525 * 4}
        for filename, expected_size in expected_sizes.items():
            if (shard / filename).stat().st_size != expected_size:
                raise ValueError(f"worker {worker} has an invalid {filename} size")
        for name, expected_hash in manifest["files"].items():
            path = shard / name
            if sha(path) != expected_hash:
                raise ValueError(f"worker {worker} output hash mismatch: {name}")
        with gzip.open(shard / "histories.jsonl.gz", "rt") as audit_file:
            audit_rows = sum(1 for line in audit_file if line.strip())
        if audit_rows != manifest["rows"]:
            raise ValueError(f"worker {worker} audit row count differs")
        entries.append(dict(worker=worker, **manifest["registry_entry"]))
        shard_ids.extend(ids)
        total_rows += manifest["rows"]
        manifests.append(dict(path=str(manifest_path), sha256=sha(manifest_path), rows=manifest["rows"]))

    if len(manifests) != args.workers:
        raise ValueError("one or more workers failed; do not create a merged registry")
    if len(set(shard_ids)) != len(shard_ids):
        raise ValueError("setup IDs repeat across worker shards")
    check_setup_id_disjoint(shard_ids, excluded)
    expected_rows = sum(int(json.loads((args.output / f"shard-{i:02d}" / "manifest.json").read_text())["rows"])
                        for i in range(args.workers))
    if total_rows != expected_rows:
        raise AssertionError("merged row count mismatch")
    setup_ids_path = args.output / "setup_ids.txt"
    setup_ids_path.write_text("".join(f"{value}\n" for value in sorted(shard_ids)))
    low32_ids_path = args.output / "setup_ids_low32.txt"
    low32_ids = sorted(value % 2**32 for value in shard_ids)
    if len(low32_ids) != len(set(low32_ids)):
        raise ValueError("merged low-32-bit setup IDs are not unique")
    low32_ids_path.write_text("".join(f"{value}\n" for value in low32_ids))
    registry = dict(schema="sprint48-offline-label-registry-v1", split=args.split,
        source_sha256=plan["source_sha256"], learner_descriptor_sha256=plan["learner_descriptor_sha256"],
        rows=total_rows, setup_count=len(shard_ids), setup_ids_file=setup_ids_path.name,
        setup_ids_sha256=sha(setup_ids_path), low32_setup_ids_file=low32_ids_path.name,
        low32_setup_ids_sha256=sha(low32_ids_path), low32_setup_count=len(low32_ids),
        worker_manifests=manifests,
        entries=entries, no_mutation_of_existing_registry=True)
    return registry


def stop_workers(procs: list[tuple[subprocess.Popen, object, dict]]) -> None:
    for process, _, _ in procs:
        if process.poll() is None:
            process.terminate()
    for process, _, _ in procs:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--learner-descriptor", type=Path, required=True)
    parser.add_argument("--policy-binary", type=Path, default=DEFAULT_POLICY_BINARY)
    parser.add_argument("--strength-binary", type=Path, default=DEFAULT_STRENGTH_BINARY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "dev"), required=True)
    parser.add_argument("--max-blocks", type=int, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--teacher-master", type=int, required=True)
    parser.add_argument("--feature-master", type=int, required=True)
    parser.add_argument("--exclude-setup-ids", type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", default=[])
    parser.add_argument("--pilot-manifest", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--invariance-checks", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=14400,
                        help="maximum worker run time; default is four hours")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.max_blocks < 1 or args.invariance_checks < 0 or args.timeout_seconds < 1:
        parser.error("workers, max-blocks, and timeout must be positive; invariance-checks must be nonnegative")

    start = time.monotonic()
    plan, metadata, blocks, skip_ids, excluded, combined_exclusions = build_plan(args)
    skip_file = args.output / "skip-setup-ids.txt"
    commands = commands_for(args, plan, skip_file, combined_exclusions)
    plan["commands"] = commands
    plan["created_utc"] = utc_now()
    plan_path = args.output / "plan.json"
    write_json(plan_path, plan)
    logs = args.output / "logs"
    logs.mkdir()
    run = dict(schema="sprint48-offline-label-run-result-v1", status="running",
        plan=str(plan_path), plan_sha256=sha(plan_path), started_utc=utc_now(), workers=[])
    run_path = args.output / "run.json"
    write_json(run_path, run)
    procs = []
    launch_failures = []
    for worker, command in enumerate(commands):
        log_path = logs / f"worker-{worker:02d}.log"
        log = log_path.open("wb")
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except Exception as error:
            log.write(f"launch failed: {type(error).__name__}: {error}\n".encode())
            log.close()
            item = dict(worker=worker, pid=None, command=command, log=str(log_path),
                        log_sha256=sha(log_path), start_utc=utc_now(), end_utc=utc_now(),
                        exit_code=-1, launch_error=f"{type(error).__name__}: {error}")
            run["workers"].append(item)
            launch_failures.append(item)
            for not_started in range(worker + 1, len(commands)):
                run["workers"].append(dict(worker=not_started, pid=None,
                    command=commands[not_started], log=None, log_sha256=None,
                    start_utc=None, end_utc=utc_now(), exit_code=-2,
                    failure="not started after an earlier launch failure"))
            break
        item = dict(worker=worker, pid=process.pid, command=command, log=str(log_path),
                    log_sha256=None, start_utc=utc_now(), exit_code=None)
        run["workers"].append(item)
        run["updated_utc"] = utc_now()
        write_json(run_path, run)
        procs.append((process, log, item))

    timed_out = False
    deadline = time.monotonic() + args.timeout_seconds
    try:
        if launch_failures:
            stop_workers(procs)
        else:
            for process, _, item in procs:
                try:
                    item["exit_code"] = process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    break
            if timed_out:
                stop_workers(procs)
        for process, log, item in procs:
            if item["exit_code"] is None:
                item["exit_code"] = process.poll()
            item["end_utc"] = utc_now()
            log.close()
            item["log_sha256"] = sha(Path(item["log"]))
            item["timed_out"] = timed_out and item["exit_code"] != 0
            write_json(run_path, run)
    except KeyboardInterrupt:
        stop_workers(procs)
        run["interrupted"] = True
        for process, log, item in procs:
            item["exit_code"] = process.poll()
            item["end_utc"] = utc_now()
            if not log.closed:
                log.close()
            item["log_sha256"] = sha(Path(item["log"]))
        run["status"] = "interrupted"
        run["failures"] = [dict(worker=item["worker"], pid=item["pid"],
                                 exit_code=item["exit_code"], log=item["log"])
                            for item in run["workers"]]
        run["ended_utc"] = utc_now()
        run["source_unchanged"] = sha(Path(plan["source"])) == plan["source_sha256"]
        write_json(run_path, run)
        raise

    failures = [dict(worker=w["worker"], pid=w["pid"], exit_code=w["exit_code"], log=w["log"])
                for w in run["workers"] if w["exit_code"] != 0]
    run["failures"] = failures
    run["seconds"] = time.monotonic() - start
    run["source_unchanged"] = sha(Path(plan["source"])) == plan["source_sha256"]
    run["timed_out"] = timed_out
    run["immutable_inputs_unchanged"] = {
        path: sha(Path(path)) == expected_hash
        for path, expected_hash in plan["immutable_files"].items()}
    run["status"] = "failed" if (failures or timed_out or not run["source_unchanged"]
                                  or not all(run["immutable_inputs_unchanged"].values())) else "verifying"
    write_json(run_path, run)
    if failures or not run["source_unchanged"]:
        print(json.dumps(run, indent=2))
        return 1

    try:
        registry = verify_shards(args, plan, commands, run["workers"], excluded)
        registry_path = args.output / "registry-entries.json"
        write_json(registry_path, registry)
        run["registry"] = str(registry_path)
        run["registry_sha256"] = sha(registry_path)
        run["status"] = "complete"
    except Exception as error:
        run["status"] = "verification_failed"
        run["verification_error"] = f"{type(error).__name__}: {error}"
        write_json(run_path, run)
        raise
    run["ended_utc"] = utc_now()
    run["seconds"] = time.monotonic() - start
    write_json(run_path, run)
    print(json.dumps(dict(status=run["status"], output=str(args.output),
        blocks=len(plan["eligible_blocks"]), skipped_setup_ids=sorted(skip_ids),
        shards=args.workers, registry=run["registry"], registry_sha256=run["registry_sha256"],
        seconds=run["seconds"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
