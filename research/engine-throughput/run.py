#!/usr/bin/env python3
"""Retain commands, failures and provenance for canonical engine profiles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/research/engine-throughput/target"
AHIN = ROOT / "local/strength/external/ahinlendor"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory():
    files = [ROOT / "Cargo.toml", ROOT / "Cargo.lock", ROOT / "rust-toolchain.toml", ROOT / "research/engine-throughput/SUITE.json"]
    for folder in ["crates/splendor-core", "crates/splendor-agents", "crates/splendor-arena", "research/engine-throughput", "research/ahinlendor/engine/trajectory"]:
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in {".rs", ".toml", ".cpp", ".py", ".bin"}]
    files += [AHIN / "game_logic.cpp", AHIN / "game_logic.h"]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(files))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=[424262])
    parser.add_argument("--games", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--with-original-baseline", action="store_true")
    parser.add_argument("--prepared-checked-only", action="store_true")
    args = parser.parse_args()
    if args.prepared_checked_only and args.with_original_baseline:
        parser.error("prepared checked replay does not use the original enumeration baseline")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise SystemExit("output must be empty")
    receipt = {"start_utc": datetime.now(timezone.utc).isoformat(), "games": args.games,
               "profile": "prepared_native_checked_apply_only" if args.prepared_checked_only else "all_profiles",
               "repeats": args.repeats, "seeds": args.seeds, "commands": [],
               "source_before": inventory(), "platform": platform.platform(),
               "load_start": os.getloadavg(), "cpu_count": os.cpu_count()}

    def save():
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

    def run(name, command, required=True, timeout=600):
        record = {"name": name, "command": [str(x) for x in command],
                  "load_before": os.getloadavg(), "utc": datetime.now(timezone.utc).isoformat()}
        receipt["commands"].append(record)
        save()
        start = time.monotonic()
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = str(TARGET)
        with (out / f"{name}.stdout").open("w") as stdout, (out / f"{name}.stderr").open("w") as stderr:
            try:
                result = subprocess.run(record["command"], cwd=ROOT, env=env, stdout=stdout, stderr=stderr, timeout=timeout)
                record["returncode"] = result.returncode
            except subprocess.TimeoutExpired:
                record["returncode"] = "timeout"
        record.update(seconds=time.monotonic() - start, load_after=os.getloadavg())
        save()
        if required and record["returncode"] != 0:
            raise SystemExit(f"{name} failed; logs retained")
        return record["returncode"] == 0

    run("upstream-pin", ["git", "-C", AHIN, "rev-parse", "HEAD"])
    if (out / "upstream-pin.stdout").read_text().strip() != "96e6f2daff83147495826c4a2073dc3c9c856cc9":
        raise SystemExit("upstream pin mismatch")
    for name, command in [("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]), ("clang", ["clang++", "--version"]),
                          ("host", ["sysctl", "-n", "machdep.cpu.brand_string"]),
                          ("processes", ["ps", "-Ao", "pid,pcpu,comm"])]:
        run(name, command)
    rust = TARGET / "release/examples/engine_profile"
    cpp = TARGET / "ahin_profile"
    if not args.skip_build:
        run("rust-build", ["cargo", "build", "--release", "--locked", "-p", "splendor-arena", "--features", "benchmark-compat", "--example", "engine_profile"])
        run("cpp-build", ["clang++", "-std=c++17", "-O3", "-DNDEBUG", "-flto", "-I", AHIN,
                          ROOT / "research/engine-throughput/ahin_profile.cpp", AHIN / "game_logic.cpp", "-o", cpp])
    receipt["binaries"] = {str(p.relative_to(ROOT)): sha(p) for p in [rust, cpp]}
    baseline = ROOT / "local/research/engine-throughput/baseline-target/release/examples/engine_baseline"
    if args.with_original_baseline:
        receipt["binaries"][str(baseline.relative_to(ROOT))] = sha(baseline)
        receipt["baseline_source_receipt_sha256"] = sha(ROOT / "local/research/engine-throughput/baseline-source.json")
    save()
    # Each Rust run writes and verifies its trace before timing. For odd seeds,
    # create it with one excluded replay first, then time C++ before Rust.
    for index, seed in enumerate(args.seeds):
        trace = out / f"seed-{seed}.txt"
        rust_command = [rust, trace, str(seed), str(args.games), str(args.repeats)]
        cpp_command = [cpp, "--repeats", str(args.repeats), "--iterations", str(args.games), trace]
        if args.prepared_checked_only:
            rust_command.append("--checked-apply-only")
            cpp_command.append("--prepared-checked-only")
        if index % 2:
            prepare_command = [rust, trace, str(seed), "1", "1"]
            if args.prepared_checked_only:
                prepare_command.append("--checked-apply-only")
            if not run(f"prepare-{seed}", prepare_command, required=False):
                continue
            before_trace = sha(trace)
            run(f"cpp-{seed}", cpp_command, required=False)
            run(f"rust-{seed}", rust_command, required=False)
            if sha(trace) != before_trace:
                raise SystemExit("trace changed between engines")
        elif run(f"rust-{seed}", rust_command, required=False):
            run(f"cpp-{seed}", cpp_command, required=False)
        if trace.exists():
            rust_log = (out / f"rust-{seed}.stderr").read_text()
            cpp_log_path = out / f"cpp-{seed}.stderr"
            if cpp_log_path.exists():
                cpp_log = cpp_log_path.read_text()
                rust_winners = re.search(r"outcome_winners_mask=(\d+)", rust_log)
                cpp_winners = re.search(r"outcome_winners_mask=(\d+)", cpp_log)
                if rust_winners and cpp_winners and rust_winners.group(1) != cpp_winners.group(1):
                    raise SystemExit("cross-engine outcome mismatch")
                receipt.setdefault("outcome_checks", {})[str(seed)] = {
                    "rust": rust_winners.group(1) if rust_winners else None,
                    "cpp": cpp_winners.group(1) if cpp_winners else None,
                    "matched": bool(rust_winners and cpp_winners and rust_winners.group(1) == cpp_winners.group(1))}
            trace_hash = sha(trace)
            receipt.setdefault("trace_sha256", {})[str(seed)] = trace_hash
            if seed == 424262 and trace_hash != "1c34dbb446f085cd56f85c274bb783b88bff5034a5adfc6d9b7b9e9a685f6d9d":
                raise SystemExit("original trace regression hash differs")
            if args.with_original_baseline:
                baseline_trace = out / f"baseline-{seed}.txt"
                run(f"baseline-{seed}", [baseline, baseline_trace, str(seed), str(args.games), str(args.repeats)])
                if sha(baseline_trace) != trace_hash:
                    raise SystemExit("original baseline trace differs from optimized trace")
        save()
    receipt["source_after"] = inventory()
    receipt["source_stable"] = receipt["source_after"] == receipt["source_before"]
    receipt["binary_after"] = {str(p.relative_to(ROOT)): sha(p) for p in [rust, cpp] + ([baseline] if args.with_original_baseline else [])}
    receipt["binary_stable"] = receipt["binary_after"] == receipt["binaries"]
    receipt["all_commands_succeeded"] = all(r["returncode"] == 0 for r in receipt["commands"])
    receipt["end_utc"] = datetime.now(timezone.utc).isoformat()
    save()
    if not receipt["source_stable"] or not receipt["binary_stable"]:
        raise SystemExit("source or binary changed during measurement; retain as invalid")
    if not receipt["all_commands_succeeded"]:
        raise SystemExit("a measured command failed; logs retained")
    print(out)


if __name__ == "__main__":
    main()
