#!/usr/bin/env python3
"""Copy the registered production champion and write cache-versioned metadata."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


WEB_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = WEB_DIR.parent
CANONICAL_ROOT = Path("/Users/payton.jones/dev/splendorust")


def source_root() -> tuple[Path, dict[str, object]]:
    configured = os.environ.get("SPLENDORUST_ROOT")
    candidates = [REPO_DIR]
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(CANONICAL_ROOT)
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        champion_path = candidate / "research/CHAMPION.json"
        if not champion_path.is_file():
            continue
        champion = json.loads(champion_path.read_text(encoding="utf-8"))
        relative_model = champion.get("model")
        if isinstance(relative_model, str) and (candidate / relative_model).is_file():
            return candidate, champion
    raise SystemExit("Could not find research/CHAMPION.json and its model in this checkout or canonical SplendoRust root.")


def main() -> None:
    root, champion = source_root()
    relative_model = champion.get("model")
    if not isinstance(relative_model, str) or not relative_model:
        raise SystemExit("CHAMPION.json must name its production model in the model field.")

    model_path = root / relative_model
    if not model_path.is_file():
        raise SystemExit(f"Champion model is missing: {model_path}")

    model_bytes = model_path.read_bytes()
    model_hash = hashlib.sha256(model_bytes).hexdigest()
    declared_hash = champion.get("model_sha256")
    if declared_hash != model_hash:
        raise SystemExit(f"Champion model SHA-256 mismatch: metadata says {declared_hash}, actual is {model_hash}.")

    model_dir = WEB_DIR / "public/models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_name = f"{model_hash}.bin"
    destination = model_dir / model_name
    if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != model_hash:
        temporary = destination.with_suffix(".bin.tmp")
        temporary.write_bytes(model_bytes)
        temporary.replace(destination)
    for stale_model in model_dir.glob("*.bin"):
        if stale_model != destination:
            stale_model.unlink()

    payload = {
        "schema": "splendor-web-champion-v1",
        "id": Path(relative_model).parts[1] if len(Path(relative_model).parts) > 1 else "champion",
        "name": f"SplendoRust {Path(relative_model).parts[1].upper()}" if len(Path(relative_model).parts) > 1 else "SplendoRust champion",
        "model": {
            "url": f"/models/{model_name}",
            "sha256": model_hash,
            "bytes": len(model_bytes),
        },
        "search": {
            "agent": champion.get("search_agent"),
            "iterations": champion.get("iterations"),
            "depth": champion.get("depth"),
            **champion.get("search_config", {}),
        },
        "source": {
            "path": relative_model,
            "sha256": model_hash,
            "scope": champion.get("scope"),
        },
    }
    checkpoint = champion.get("checkpoint")
    if checkpoint:
        payload["source"]["checkpoint"] = checkpoint
    checkpoint_hash = champion.get("checkpoint_sha256")
    if checkpoint_hash:
        payload["source"]["checkpoint_sha256"] = checkpoint_hash

    metadata_path = WEB_DIR / "public/champion.json"
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Champion metadata ready: {metadata_path.relative_to(WEB_DIR)}")
    print(f"Model: {payload['model']['url']} ({len(model_bytes):,} bytes; sha256 {model_hash})")


if __name__ == "__main__":
    main()
