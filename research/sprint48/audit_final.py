#!/usr/bin/env python3
"""Independently audit a completed, frozen Sprint 48 final campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/sprint48"))
import freeze

RUN_PATH = ROOT / "research/sprint48/RUN.json"
EVIDENCE_KEYS = (
    "games", "setup_blocks", "statuses", "terminal_categories",
    "all_requested_credit_bounds", "conservative_hoeffding95_missing_envelope",
    "caps_as_unknown_credit_bounds", "caps_as_unknown_hoeffding95", "radius",
    "evidence_rejections", "decisive_native_criterion", "decisive_with_caps_unknown",
)
SUMMARY_KEYS = (
    "schema_version", "games", "setup_blocks", "statuses", "incomplete_games",
    "invalid_games", "unsupported_games", "blocked_games", "capped_games",
    "candidate_credit_total", "candidate_credit_conditional_rate", "all_requested_credit_bounds",
    "paired_bootstrap95_missing_envelope", "conservative_hoeffding95_missing_envelope",
    "terminal_categories", "elapsed_game_seconds", "wall_seconds", "policy_seconds",
    "simulations", "inferences",
)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require_complete(run: dict, private: dict, output: Path) -> None:
    campaign = run.get("final_campaign")
    if run.get("schema") != "splendorust-strength-sprint-run-v1" or not isinstance(campaign, dict):
        raise ValueError("RUN.json has no registered final campaign")
    if campaign.get("status") != "complete" or private.get("status") != "complete":
        raise ValueError("final audit waits for RUN and private campaign status complete")
    if campaign.get("output") is None or Path(campaign["output"]).resolve() != output.resolve():
        raise ValueError("RUN final output differs from audit output")
    if private.get("schema") != "sprint48-final-run-v1" or private.get("output") is None:
        raise ValueError("private final run receipt schema or output is invalid")
    if Path(private["output"]).resolve() != output.resolve():
        raise ValueError("private final run output differs")
    if private.get("campaign_id") != campaign.get("id"):
        raise ValueError("RUN and private campaign IDs differ")
    if private.get("master") != freeze.MASTER or private.get("games") != 1000:
        raise ValueError("private final count or master differs from the frozen campaign")


def setup_seed(master: int, block: int) -> int:
    digest = hashlib.sha256(f"native-v1:{master}:setup:{block}:0".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def validate_raw(raw_path: Path, metadata: dict, games: int = 1000) -> tuple[list[dict], str]:
    raw = Path(raw_path).read_bytes()
    try:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid raw game JSON: {error}") from error
    if len(records) != games + 1 or records[0] != metadata:
        raise ValueError("raw file does not contain one header and the full fixed game count")
    if (metadata.get("games") != games or metadata.get("campaign_games") != games
            or metadata.get("master") != freeze.MASTER or metadata.get("offset_block") != 0):
        raise ValueError("raw header count, master, or starting block differs")
    rows = records[1:]
    seen = set()
    for block in range(games // 2):
        pair = rows[2 * block:2 * block + 2]
        if [row.get("index") for row in pair] != [2 * block, 2 * block + 1]:
            raise ValueError(f"raw game indices are missing or unordered in block {block}")
        if ([row.get("block") for row in pair] != [block, block]
                or [row.get("rotation") for row in pair] != [0, 1]
                or [row.get("seats") for row in pair] != [["champion", "alphazero"], ["alphazero", "champion"]]):
            raise ValueError(f"raw pair rotation differs in block {block}")
        seed = setup_seed(freeze.MASTER, block)
        if any(row.get("setup_seed") != seed for row in pair) or seed in seen:
            raise ValueError(f"raw setup seed differs or repeats in block {block}")
        if pair[0].get("initial_state") != pair[1].get("initial_state"):
            raise ValueError(f"paired initial states differ in block {block}")
        seen.add(seed)
    if len(seen) != games // 2:
        raise ValueError("raw file does not contain 500 unique setup blocks")
    return rows, hashlib.sha256(raw).hexdigest()


def compare_metrics(original: dict, regenerated: dict, keys: tuple[str, ...], label: str) -> None:
    for key in keys:
        if key not in original or key not in regenerated or original[key] != regenerated[key]:
            raise ValueError(f"{label} metric differs after regeneration: {key}")


def _run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"audit command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}")


def audit(output: Path, run_path: Path = RUN_PATH) -> dict:
    output = Path(output).resolve(strict=True)
    run = read_json(run_path)
    private_path = output / "run.json"
    private = read_json(private_path)
    require_complete(run, private, output)

    freeze_path = Path(private.get("freeze_path", "")).resolve(strict=True)
    if freeze_path.parent != output:
        raise ValueError("freeze is not in the completed campaign output")
    frozen = read_json(freeze_path)
    freeze.validate_freeze(frozen)
    freeze_digest = frozen["freeze_sha256"]
    if private.get("freeze_sha256") != freeze_digest or run["final_campaign"].get("freeze_sha256") != freeze_digest:
        raise ValueError("RUN/private receipt does not bind the final freeze")

    context = read_json(Path(private.get("campaign_context_path", "")))
    if (context.get("schema") != "sprint48-final-campaign-context-v1"
            or context.get("freeze_sha256") != freeze_digest):
        raise ValueError("campaign context schema or freeze hash differs")
    if context.get("campaign_started_at_utc") != private.get("campaign_started_at_utc"):
        raise ValueError("campaign start timestamp differs from private receipt")

    for relative, digest in frozen["source_sha256"].items():
        if freeze.sha(ROOT / relative) != digest:
            raise ValueError(f"current source differs from freeze: {relative}")
        copied = output / "sources" / relative
        if not copied.is_file() or freeze.sha(copied) != digest:
            raise ValueError(f"copied frozen source differs: {relative}")
    candidate = frozen["candidate"]
    artifacts = [candidate[key] for key in ("checkpoint", "descriptor", "export_receipt")]
    artifacts.extend(candidate["binaries"].values())
    for artifact in artifacts:
        path = Path(artifact["path"])
        if not path.is_file() or freeze.sha(path) != artifact["sha256"]:
            raise ValueError(f"current frozen artifact hash differs: {path}")
    export = read_json(Path(candidate["export_receipt"]["path"]))
    if (export.get("checkpoint_sha256") != candidate["checkpoint"]["sha256"]
            or export.get("descriptor_sha256") != candidate["descriptor"]["sha256"]):
        raise ValueError("export receipt does not bind frozen checkpoint and descriptor")

    raw_path = output / "arena/games.jsonl"
    raw_meta_line = raw_path.read_text().splitlines()[0]
    metadata = json.loads(raw_meta_line)
    rows, raw_hash = validate_raw(raw_path, metadata, frozen["evaluation"]["games"])
    if private.get("raw_sha256") != raw_hash:
        raise ValueError("private receipt raw hash differs")

    replay_path = output / "replay.json"
    replay = read_json(replay_path)
    replay_schema = {"checked_games", "checked_transitions", "raw_sha256", "script_sha256", "upstream_revision", "scope"}
    if (set(replay) != replay_schema or replay.get("checked_games") != 1000
            or not isinstance(replay.get("checked_transitions"), int)
            or replay.get("checked_transitions") < 0 or replay.get("raw_sha256") != raw_hash
            or replay.get("upstream_revision") != frozen["target"]["revision"]):
        raise ValueError("owned replay receipt schema, game count, or raw hash differs")
    replay_source = "benchmarks/strength/native/replay.py"
    if (replay.get("script_sha256") != frozen["source_sha256"].get(replay_source)
            or private.get("replay_sha256") != freeze.sha(replay_path)):
        raise ValueError("owned replay source or receipt hash differs")

    evidence_path = output / "evidence.json"
    evidence = read_json(evidence_path)
    evidence_source = "research/sprint48/evidence.py"
    if (evidence.get("raw_sha256") != raw_hash
            or evidence.get("script_sha256") != frozen["source_sha256"].get(evidence_source)
            or private.get("evidence_sha256") != freeze.sha(evidence_path)):
        raise ValueError("owned evidence source, raw hash, or receipt hash differs")

    summary_path = output / "summary.json"
    summary = read_json(summary_path)
    summary_source = "benchmarks/strength/native/summarize.py"
    if (summary.get("schema_version") != 2 or summary.get("raw_sha256") != raw_hash
            or summary.get("source_sha256") != frozen["source_sha256"].get(summary_source)
            or private.get("summary_sha256") != freeze.sha(summary_path)):
        raise ValueError("owned summary source, raw hash, or receipt hash differs")

    if (private.get("games_verified") != 1000 or replay["checked_games"] != 1000
            or metadata.get("freeze_sha256") != freeze_digest):
        raise ValueError("private completion or replay does not bind 1000 frozen games")
    audit_dir = output / "independent-audit"
    audit_dir.mkdir(exist_ok=False)
    evidence_script = output / "sources" / evidence_source
    _run([sys.executable, str(evidence_script), str(raw_path), "--output", str(audit_dir / "evidence.json")])
    # The bound native wrapper is checked above. Its imported generic summary
    # module is a diagnostic dependency and is recorded separately below.
    summary_script = ROOT / summary_source
    _run([sys.executable, str(summary_script), str(raw_path), "--output", str(audit_dir / "summary.json")])
    regenerated_evidence = read_json(audit_dir / "evidence.json")
    regenerated_summary = read_json(audit_dir / "summary.json")
    compare_metrics(evidence, regenerated_evidence, EVIDENCE_KEYS, "evidence")
    compare_metrics(summary, regenerated_summary, SUMMARY_KEYS, "summary")
    if regenerated_evidence.get("raw_sha256") != raw_hash or regenerated_summary.get("raw_sha256") != raw_hash:
        raise ValueError("regenerated reports do not bind the raw game file")
    claim_supported = freeze.validate_outcomes(frozen, metadata, regenerated_evidence,
        context["campaign_started_at_utc"], 1000)

    radius = math.sqrt(math.log(40) / (2 * 500))
    report = {
        "schema": "sprint48-independent-final-audit-v1", "status": "complete",
        "freeze_sha256": freeze_digest, "raw_sha256": raw_hash,
        "games": 1000, "setup_blocks": 500,
        "statuses": evidence["statuses"],
        "no_action_fraction": evidence["statuses"].get("no_legal_action", 0) / 1000,
        "native_turn_cap_count": evidence["terminal_categories"].get("native_turn_cap", 0),
        "all_requested_credit_bounds": evidence["all_requested_credit_bounds"],
        "primary_hoeffding95": evidence["conservative_hoeffding95_missing_envelope"],
        "primary_hoeffding_radius": radius,
        "caps_as_unknown_credit_bounds": evidence["caps_as_unknown_credit_bounds"],
        "caps_as_unknown_hoeffding95": evidence["caps_as_unknown_hoeffding95"],
        "claim_supported": claim_supported,
        "replay_checked_transitions": replay["checked_transitions"],
        "simulations": summary.get("simulations"), "inferences": summary.get("inferences"),
        "wall_seconds": summary.get("wall_seconds"),
        "audit_evidence_path": str(audit_dir / "evidence.json"),
        "audit_summary_path": str(audit_dir / "summary.json"),
        "summary_support_sha256": freeze.sha(ROOT / "benchmarks/strength/summarize.py"),
    }
    freeze._atomic_json(audit_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local/research/sprint48/final-native-retry")
    parser.add_argument("--run", type=Path, default=RUN_PATH)
    args = parser.parse_args()
    print(json.dumps(audit(args.output, args.run), sort_keys=True))


if __name__ == "__main__":
    main()
