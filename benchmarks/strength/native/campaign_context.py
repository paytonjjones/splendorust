"""Validate a frozen final campaign context before native shard execution."""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path


def campaign_metadata(path, args, root: Path, model: Path, policy_binary: Path,
                      strength_binary: Path, external_config: dict) -> dict:
    if path is None:
        return {}
    root = Path(root).resolve(strict=True)
    sprint_tools = root / "research/sprint48"
    if str(sprint_tools) not in sys.path:
        sys.path.insert(0, str(sprint_tools))
    module_name = "sprint48_final_freeze"
    final_freeze = sys.modules.get(module_name)
    if final_freeze is None:
        spec = importlib.util.spec_from_file_location(module_name, sprint_tools / "freeze.py")
        final_freeze = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = final_freeze
        spec.loader.exec_module(final_freeze)

    context_path = Path(path).resolve(strict=True)
    context = json.loads(context_path.read_text())
    required = {"schema", "freeze_path", "freeze_sha256", "campaign_started_at_utc",
        "checkpoint_path", "checkpoint_sha256", "export_receipt_path", "export_receipt_sha256",
        "parity_binary_path", "parity_binary_sha256", "service_config", "source_sha256"}
    if set(context) != required or context.get("schema") != "sprint48-final-campaign-context-v1":
        raise ValueError("invalid final campaign context schema")
    frozen_path = Path(context["freeze_path"]).resolve(strict=True)
    manifest = json.loads(frozen_path.read_text())
    final_freeze.validate_freeze(manifest)
    if manifest["freeze_sha256"] != context["freeze_sha256"]:
        raise ValueError("campaign context does not bind the final freeze")
    started = datetime.datetime.fromisoformat(context["campaign_started_at_utc"].replace("Z", "+00:00"))
    frozen = datetime.datetime.fromisoformat(manifest["frozen_at_utc"].replace("Z", "+00:00"))
    if started.tzinfo is None or started <= frozen:
        raise ValueError("campaign start must follow freeze time")
    evaluation, search = manifest["evaluation"], manifest["search"]
    candidate, binaries = manifest["candidate"], manifest["candidate"]["binaries"]
    campaign_games = getattr(args, "campaign_games", None)
    if campaign_games != evaluation["games"]:
        raise ValueError("shard campaign game count differs from frozen protocol")
    if (args.games <= 0 or args.games % 2 or args.offset_block < 0 or
            args.offset_block + args.games // 2 > campaign_games // 2):
        raise ValueError("shard block range exceeds frozen campaign")
    expected_settings = (evaluation["games"], evaluation["master"], search["algorithm"],
        search["iterations"], search["depth"], search["world_pool"], search["chance_universes"],
        search["gumbel_max_considered"] or 16, search["dynamic_fpu"], search["root_only"])
    actual_settings = (campaign_games, args.master, args.search, args.iterations, args.depth,
        args.world_pool, args.chance_universes, args.gumbel_max_considered,
        args.dynamic_fpu, args.root_only)
    if actual_settings != expected_settings:
        raise ValueError("native run settings differ from frozen protocol")
    if str(model) != candidate["descriptor"]["path"] or final_freeze.sha(model) != candidate["descriptor"]["sha256"]:
        raise ValueError("candidate descriptor differs from freeze")
    for name, path_value in (("native_policy_worker", policy_binary), ("strength_worker", strength_binary)):
        if str(path_value) != binaries[name]["path"] or final_freeze.sha(path_value) != binaries[name]["sha256"]:
            raise ValueError(f"{name} differs from freeze")
    artifacts = ((context["checkpoint_path"], context["checkpoint_sha256"], candidate["checkpoint"]),
        (context["export_receipt_path"], context["export_receipt_sha256"], candidate["export_receipt"]),
        (context["parity_binary_path"], context["parity_binary_sha256"], binaries["transfer_parity"]))
    for path_value, digest, expected in artifacts:
        artifact = Path(path_value).resolve(strict=True)
        if str(artifact) != expected["path"] or final_freeze.sha(artifact) != digest or digest != expected["sha256"]:
            raise ValueError("campaign artifact differs from freeze")
    if external_config != manifest["target"]["external_config"]:
        raise ValueError("AlphaZero settings differ from frozen target")
    service = manifest["service"]
    expected_service = {key: service[key] for key in ("backend", "batch", "delay_ms", "port", "fast_entities")}
    expected_service["source_sha256"] = service["source"]["sha256"]
    if context["service_config"] != expected_service:
        raise ValueError("service differs from freeze")
    if context["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("context source hashes differ from freeze")
    for relative, digest in context["source_sha256"].items():
        if final_freeze.sha(root / relative) != digest:
            raise ValueError(f"current source differs from freeze: {relative}")
    return {"campaign_games": campaign_games,
        "campaign_freeze_path": str(frozen_path), "freeze_sha256": manifest["freeze_sha256"],
        "campaign_started_at_utc": context["campaign_started_at_utc"],
        "campaign_context_path": str(context_path), "campaign_context_sha256": final_freeze.sha(context_path),
        "checkpoint_path": context["checkpoint_path"], "checkpoint_sha256": context["checkpoint_sha256"],
        "export_receipt_path": context["export_receipt_path"],
        "export_receipt_sha256": context["export_receipt_sha256"],
        "parity_binary_path": context["parity_binary_path"],
        "parity_binary_sha256": context["parity_binary_sha256"],
        "service_config": context["service_config"], "source_sha256": context["source_sha256"]}
