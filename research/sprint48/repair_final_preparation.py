"""Review and, only with --apply, clear a failed pre-freeze final reservation.

This helper is intentionally narrow. It keeps the failed output in place and
records its complete file hashes in RUN.json before it clears the reservation.
It does not make or change a seed, freeze, schedule, or result.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUN_PATH = ROOT / "research/sprint48/RUN.json"
FAILED_OUTPUT = ROOT / "local/research/sprint48/final-native"
RETRY_OUTPUT = ROOT / "local/research/sprint48/final-native-retry"
EXPECTED_CAMPAIGN = "fa20838c17984bae8d146b0e9207d965"


def _load_freeze():
    path = ROOT / "research/sprint48/freeze.py"
    spec = importlib.util.spec_from_file_location("sprint48_repair_freeze", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load freeze module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON receipt {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"receipt is not a JSON object: {path}")
    return value


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _sha_value(value) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def pid_is_alive(pid: int) -> bool:
    """Return true when the PID exists or access to it is denied."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tree_hashes(output: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"failed output contains a symlink: {path}")
        if path.is_file():
            files[path.relative_to(output).as_posix()] = _sha_file(path)
    if not files:
        raise ValueError("failed output has no retained files")
    return files


def _check_no_game_or_freeze_artifacts(output: Path) -> None:
    for path in output.rglob("*"):
        relative = path.relative_to(output)
        parts = {part.lower() for part in relative.parts}
        name = path.name.lower()
        if ("arena" in parts or "arena-command" in parts or "outcomes" in parts or
                "schedule" in parts):
            raise ValueError(f"game or schedule artifacts exist: {relative}")
        if name.startswith("final-freeze") or name in {"freeze.json", "schedule.jsonl"}:
            raise ValueError(f"freeze or schedule artifact exists: {relative}")
        if name.endswith((".jsonl", ".jsonl.gz")):
            raise ValueError(f"game record file exists: {relative}")
        if name == "process.json" and relative.as_posix() != "parity-command/process.json":
            raise ValueError(f"unexpected process evidence exists: {relative}")


def inspect_attempt(run_path: Path, expected_campaign_id: str,
                    retry_output: Path) -> dict:
    """Validate all preconditions and return a hash-bound history record."""
    run_path = run_path.resolve(strict=True)
    retry_output = retry_output.resolve()
    run = _json(run_path)
    campaign = run.get("final_campaign")
    selection = run.get("final_selection")
    if run.get("status") != "active" or run.get("final_seed_sealed") is not True:
        raise ValueError("RUN must be active and the registered final seed must stay sealed")
    if not isinstance(campaign, dict) or campaign.get("id") != expected_campaign_id:
        raise ValueError("RUN does not contain the expected failed campaign")
    if campaign.get("status") != "failed":
        raise ValueError("only a failed final reservation can be cleared")
    if campaign.get("seeded") is True:
        raise ValueError("campaign records seeded work")
    if any(key in campaign and campaign[key] is not None for key in
           ("schedule_pid", "freeze_path", "freeze_sha256", "seeded_at_utc")):
        raise ValueError("campaign contains evidence that it advanced past preparation")
    if not isinstance(selection, dict):
        raise ValueError("RUN has no registered final selection")
    if any(item.get("master") == campaign.get("master")
           for item in run.get("consumed_trials", []) if isinstance(item, dict)):
        raise ValueError("failed campaign master appears in consumed trials")

    output = Path(campaign.get("output", "")).resolve()
    expected_output = FAILED_OUTPUT.resolve()
    if output != expected_output:
        raise ValueError(f"failed output does not match the registered failed attempt: {output}")
    if retry_output == output or retry_output.exists():
        raise ValueError("retry output must be new and separate from the failed output")
    if not output.is_dir():
        raise ValueError("failed output directory is missing")

    receipt_path = output / "run.json"
    service_path = output / "service/run.json"
    parity_process_path = output / "parity-command/process.json"
    parity_exit_path = output / "parity-command/exit.json"
    private = _json(receipt_path)
    service = _json(service_path)
    parity_process = _json(parity_process_path)
    parity_exit = _json(parity_exit_path)
    if private.get("schema") != "sprint48-final-run-v1" or private.get("status") != "failed":
        raise ValueError("private final receipt is not the expected failed receipt")
    if private.get("campaign_id") != expected_campaign_id or private.get("output") != str(output):
        raise ValueError("private receipt campaign or output does not match RUN")
    if any(key in private and private[key] is not None for key in
           ("schedule_pid", "freeze_path", "freeze_sha256", "seeded_at_utc")):
        raise ValueError("private receipt contains schedule, freeze, or seed evidence")
    if private.get("seeded") is True:
        raise ValueError("private receipt records seeded work")
    reason = str(private.get("error", ""))
    if "cannot read" not in reason or "Is a directory" not in reason:
        raise ValueError("failure reason is not the known pre-freeze control-queue read error")
    if str(private.get("error")) != str(campaign.get("error")):
        raise ValueError("RUN and private receipt failure reasons differ")

    # Bind every registered selection field that defines the planned campaign.
    freeze_master = 17_790_000_000
    settings = {
        "master": freeze_master,
        "games": selection.get("games"),
        "search": selection.get("search"),
        "iterations": selection.get("iterations"),
        "depth": selection.get("depth"),
        "world_pool": selection.get("world_pool"),
        "chance_universes": selection.get("chance_universes"),
        "dynamic_fpu": selection.get("dynamic_fpu"),
        "gumbel_max_considered": selection.get("gumbel_max_considered"),
        "root_only": selection.get("root_only", False),
        "workers": selection.get("workers"),
        "backend": selection.get("backend"),
        "batch": selection.get("batch"),
        "checkpoint_sha256": selection.get("checkpoint_sha256"),
    }
    if campaign.get("master") != freeze_master:
        raise ValueError("failed attempt did not use the registered final master")
    for key, expected in settings.items():
        private_key = "checkpoint_source_sha256" if key == "checkpoint_sha256" else key
        if campaign.get(key) != expected or private.get(private_key) != expected:
            raise ValueError(f"registered selection mismatch for {key}")
    source = (ROOT / str(selection.get("checkpoint", ""))).resolve(strict=True)
    source_sha = _sha_file(source)
    candidate_copy = output / "input/candidate.pt"
    if source_sha != selection.get("checkpoint_sha256") or _sha_file(candidate_copy) != source_sha:
        raise ValueError("candidate checkpoint source or retained copy does not match selection")
    if private.get("checkpoint_source") != str(source) or private.get("checkpoint_source_sha256") != source_sha:
        raise ValueError("private receipt checkpoint binding does not match selection")
    if (output / "campaign-context.json").exists():
        raise ValueError("campaign context exists; preparation advanced beyond the failed reservation")

    if service.get("pid") != campaign.get("service_pid"):
        raise ValueError("service PID evidence does not match the failed campaign")
    pids = {"driver": campaign.get("driver_pid"), "service": service.get("pid"),
            "parity": parity_process.get("pid")}
    for label, pid in pids.items():
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError(f"missing or invalid {label} process PID")
        if pid_is_alive(pid):
            raise ValueError(f"{label} process is still alive: {pid}")
    if parity_exit.get("returncode") != 0:
        raise ValueError("parity process did not finish successfully")

    freeze_path = output / "final-freeze.json"
    if freeze_path.exists():
        raise ValueError("final freeze file exists")
    _check_no_game_or_freeze_artifacts(output)
    file_hashes = _tree_hashes(output)
    source_hashes = {name: digest for name, digest in file_hashes.items()
                     if name.startswith("sources/")}
    if not source_hashes:
        raise ValueError("failed output has no retained frozen source files")
    campaign_copy = json.loads(json.dumps(campaign))
    return {
        "schema": "sprint48-failed-final-preparation-v1",
        "status": "verified_pre_freeze_failure",
        "campaign_id": expected_campaign_id,
        "failed_at_utc": campaign.get("finished_at_utc", campaign.get("updated_at_utc")),
        "failed_output": str(output),
        "retry_output": str(retry_output),
        "registered_profile": "alphazero-native-32a27ac-v1",
        "registered_selection": json.loads(json.dumps(selection)),
        "final_seed_sealed": True,
        "campaign_record": campaign_copy,
        "campaign_record_sha256": _sha_value(campaign_copy),
        "private_receipt": {"path": str(receipt_path), "sha256": file_hashes["run.json"]},
        "private_service_receipt": {"path": str(service_path), "sha256": file_hashes["service/run.json"]},
        "source_sha256": source_hashes,
        "retained_output_files": file_hashes,
        "retained_output_tree_sha256": _sha_value(file_hashes),
        "processes_confirmed_dead": pids,
        "no_freeze_or_game_records": True,
        "retry_preserves_master_games_and_selection": True,
    }


def repair(run_path: Path, expected_campaign_id: str, retry_output: Path,
           apply: bool) -> dict:
    """Inspect under RUN lock; optionally append history and clear reservation."""
    freeze = _load_freeze()
    run_path = Path(run_path).resolve(strict=True)
    handle = freeze._run_lock(run_path)
    try:
        record = inspect_attempt(run_path, expected_campaign_id, retry_output)
        if apply:
            run = _json(run_path)
            # Recheck identity while holding the lock, before changing one field.
            campaign = run.get("final_campaign")
            if not isinstance(campaign, dict) or campaign.get("id") != expected_campaign_id:
                raise ValueError("campaign identity changed before repair")
            failed = run.setdefault("failed_attempts", [])
            if not isinstance(failed, list):
                raise ValueError("RUN failed_attempts is not a list")
            record["repair_applied"] = True
            failed.append(record)
            run["final_campaign"] = None
            freeze._atomic_json(run_path, run)
        else:
            record["repair_applied"] = False
        return record
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-json", type=Path, default=RUN_PATH)
    parser.add_argument("--campaign-id", default=EXPECTED_CAMPAIGN)
    parser.add_argument("--failed-output", type=Path, default=FAILED_OUTPUT,
                        help="must be the recorded output path for this known repair")
    parser.add_argument("--retry-output", type=Path, default=RETRY_OUTPUT)
    parser.add_argument("--apply", action="store_true",
                        help="append the evidence record and clear the failed reservation")
    args = parser.parse_args()
    # The known path is deliberately fixed by inspect_attempt. This option is
    # present for a visible CLI contract and rejects any attempt to broaden it.
    if args.failed_output.resolve() != FAILED_OUTPUT.resolve():
        parser.error("--failed-output must match the registered failed attempt")
    try:
        record = repair(args.run_json, args.campaign_id, args.retry_output, args.apply)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(record, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
