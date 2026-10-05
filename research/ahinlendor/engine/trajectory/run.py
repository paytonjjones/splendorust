#!/usr/bin/env python3
"""Build and run the bounded, exact-state Rust/Ahin trajectory benchmark."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
AHIN = ROOT / "local/strength/external/ahinlendor"
PIN = "96e6f2daff83147495826c4a2073dc3c9c856cc9"
RUST_TARGET = ROOT / "local/research/ahinlendor/engine/trajectory/target"
RUST_BIN = RUST_TARGET / "release/examples/engine_trajectory"
RUST_SOURCE = ROOT / "crates/splendor-arena/examples/engine_trajectory.rs"
CPP_SOURCE = ROOT / "research/ahinlendor/engine/trajectory/ahin_trajectory.cpp"
CPP_LOGIC = AHIN / "game_logic.cpp"
CPP_HEADER = AHIN / "game_logic.h"
REPLAYS = 10_000
SOURCE_PATHS = (
    Path("Cargo.toml"), Path("Cargo.lock"),
    Path("crates/splendor-arena/Cargo.toml"), Path("crates/splendor-core/src/lib.rs"),
    Path("crates/splendor-core/src/data.rs"),
    Path("crates/splendor-core/src/benchmark_compat.rs"),
    Path("crates/splendor-arena/examples/engine_trajectory.rs"),
    Path("research/ahinlendor/engine/trajectory/ahin_trajectory.cpp"),
    Path("research/ahinlendor/engine/trajectory/run.py"),
    Path("research/ahinlendor/engine/trajectory/README.md"),
    Path("local/strength/external/ahinlendor/game_logic.h"),
    Path("local/strength/external/ahinlendor/game_logic.cpp"),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command_version(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True, timeout=15)
    return (result.stdout + result.stderr).strip()


def optional_command(command: list[str]) -> str | None:
    try:
        return command_version(command)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def run_checked(command: list[str], *, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                check=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"command exceeded {timeout}s: {command[0]}") from error
    return {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed_seconds": time.monotonic() - start,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=424262)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("local/research/ahinlendor/engine/trajectory/runs/seed-424262"))
    args = parser.parse_args()
    out = (ROOT / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    ahin_commit = subprocess.run(["git", "-C", str(AHIN), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    if ahin_commit != PIN:
        raise SystemExit(f"pinned AhinLendor revision changed: {ahin_commit}")
    source_hashes_before = {str(path): sha256(ROOT / path) for path in SOURCE_PATHS}

    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(RUST_TARGET)
    cargo_command = ["cargo", "build", "--release", "--locked", "-p", "splendor-arena",
                     "--features", "benchmark-compat", "--example", "engine_trajectory"]
    cargo = run_checked(cargo_command, timeout=600, env=env)
    cpp_command = ["clang++", "-std=c++17", "-O3", "-DNDEBUG", "-flto", "-I", str(AHIN),
                   str(CPP_SOURCE), str(CPP_LOGIC), "-o", str(out / "ahin_trajectory")]
    cpp_build = run_checked(cpp_command, timeout=300)
    trace = out / "trajectory.txt"
    rust_run = run_checked([str(RUST_BIN), str(trace), str(args.seed)], timeout=120)
    cpp_run = run_checked([str(out / "ahin_trajectory"), str(trace)], timeout=120)
    if "status=complete" not in rust_run["stderr"]:
        raise SystemExit("Rust trajectory did not complete the required workload")
    if not cpp_run["stderr"].startswith("verified "):
        raise SystemExit("C++ full-state digest verification did not complete")

    trace_lines = trace.read_text().splitlines()
    for index, line in enumerate(trace_lines):
        if line.startswith("ENDTURN|0|"):
            fields = line.split("|", 3)
            snapshot = fields[3]
            fields[3] = snapshot[:-1] + ("X" if snapshot[-1] != "X" else "Y")
            trace_lines[index] = "|".join(fields)
            break
    else:
        raise RuntimeError("trajectory has no first completed-turn snapshot")
    corrupt_trace = out / "corrupt-snapshot-probe.txt"
    corrupt_trace.write_text("\n".join(trace_lines) + "\n")
    guard_command = [str(out / "ahin_trajectory"), str(corrupt_trace)]
    guard = subprocess.run(guard_command, cwd=ROOT, capture_output=True, text=True, timeout=10)
    if guard.returncode == 0 or "exact mismatch at turn 0" not in guard.stderr:
        raise RuntimeError("C++ replay did not reject the deliberately changed exact snapshot")

    def rows(output: str) -> list[dict[str, str]]:
        parsed = list(csv.DictReader(output.splitlines()))
        if len(parsed) != 3 or any(int(row["replayed_games"]) != REPLAYS for row in parsed):
            raise RuntimeError("expected exactly three repeats of the fixed replay count")
        return parsed

    rust_rows = rows(rust_run["stdout"])
    cpp_rows = rows(cpp_run["stdout"])
    for name, record in (("cargo-build", cargo), ("cpp-build", cpp_build),
                         ("rust-run", rust_run), ("cpp-run", cpp_run)):
        (out / f"{name}.stdout.txt").write_text(record["stdout"])
        (out / f"{name}.stderr.txt").write_text(record["stderr"])
    source_hashes = {str(path): sha256(ROOT / path) for path in SOURCE_PATHS}
    if source_hashes != source_hashes_before:
        raise RuntimeError("a source file changed during the run; provenance is not stable")
    (out / "snapshot-guard.stdout.txt").write_text(guard.stdout)
    (out / "snapshot-guard.stderr.txt").write_text(guard.stderr)
    report = {
        "schema": "sprint48-ahin-full-turn-benchmark-v1",
        "status": "complete_exact_state_parity",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile": "raw game-engine legal-enumeration plus fixed full-turn trace replay; no bots, weights, or hidden-state inference",
        "upstream": {"path": str(AHIN.relative_to(ROOT)), "commit": ahin_commit},
        "setup_seed": args.seed,
        "trajectory_sha256": sha256(trace),
        "replay_games_per_repeat": REPLAYS,
        "repeat_count": 3,
        "coverage": rust_run["stderr"].strip(),
        "verified_cpp_receipt": cpp_run["stderr"].strip(),
        "snapshot_corruption_guard": {"command": guard_command, "returncode": guard.returncode,
                                      "stderr": guard.stderr.strip(),
                                      "corrupt_trace_sha256": sha256(corrupt_trace)},
        "rust_build": {"command": cargo_command, "elapsed_seconds": cargo["elapsed_seconds"],
                       "flags": ["--release", "--locked", "--features benchmark-compat"],
                       "binary_sha256": sha256(RUST_BIN)},
        "cpp_build": {"command": cpp_command, "elapsed_seconds": cpp_build["elapsed_seconds"],
                      "flags": ["-std=c++17", "-O3", "-DNDEBUG", "-flto"],
                      "binary_sha256": sha256(out / "ahin_trajectory")},
        "toolchain": {"rustc": command_version(["rustc", "-Vv"]), "cargo": command_version(["cargo", "-V"]),
                      "clang": command_version(["clang++", "--version"])},
        "machine": {"platform": platform.platform(), "processor": platform.processor(),
                    "cpu_brand": optional_command(["sysctl", "-n", "machdep.cpu.brand_string"]),
                    "logical_cpu_count": os.cpu_count(),
                    "load_average_at_receipt": os.getloadavg() if hasattr(os, "getloadavg") else None},
        "source_sha256": source_hashes,
        "rust_repeats": rust_rows,
        "ahin_repeats": cpp_rows,
        "limits": {
            "unsupported_gold_return": "trajectory generation rejects it; no fallback action",
            "no_action_pass": "unsupported; no invented move",
            "timing": "fixed trace excludes policy selection and equality digest work; exact digest replay runs before timing",
            "operation_counts": "canonical bundled return/payment actions and Ahin atomic return/automatic payment calls are reported separately",
        },
    }
    (out / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output_dir": str(out), "status": report["status"],
                      "trajectory_sha256": report["trajectory_sha256"],
                      "rust_repeats": rust_rows, "ahin_repeats": cpp_rows}, indent=2))


if __name__ == "__main__":
    main()
