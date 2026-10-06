#!/usr/bin/env python3
"""Validate and time current Rust, pinned seal256, and pinned AhinLendor."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time

from make_corpus import create
from run import interval

ROOT = Path(__file__).resolve().parents[1]
BINARIES = {
    "splendorust": ROOT / "target/release/examples/aligned_worker",
    "seal256": ROOT / "local/benchmarks/external/seal256-game",
    "ahinlendor": ROOT / "local/benchmarks/external/ahin-aligned",
}
FIELDS = ["seed", "status", "turns", "final_state"]


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory():
    paths = [ROOT / p for p in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml",
                               "benchmarks/PROFILES.md", "benchmarks/refresh_aligned.py",
                               "benchmarks/make_corpus.py", "benchmarks/run.py",
                               "benchmarks/adapters/ahin_aligned.cpp",
                               "benchmarks/adapters/external_seal256_game.cpp")]
    for directory in ("crates/splendor-core", "crates/splendor-agents", "crates/splendor-arena"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and p.suffix in (".rs", ".toml"))
    for directory, names in (("local/strength/external/ahinlendor", ("game_logic.cpp", "game_logic.h")),
                             ("local/benchmarks/external/seal256/src", ("splendor.cpp", "splendor.h", "game_state.cpp", "game_state.h", "json.hpp"))):
        paths.extend(ROOT / directory / p for p in names)
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "aligned.json"
    if report_path.exists():
        raise SystemExit("refuse to overwrite an existing report")
    work = ROOT / "local/benchmarks/refresh-20261006"
    work.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "profile": "seal256-intersection-v1",
              "start_utc": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_files": inventory(), "binaries": {k: sha(p) for k, p in BINARIES.items()},
              "machine": {"os": platform.platform(), "cpu": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
                          "logical_cores": os.cpu_count(), "load_start": os.getloadavg()},
              "versions": {"rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
                           "clang": subprocess.check_output(["clang++", "--version"], text=True)},
              "threads": 1, "repetitions": 7, "pilots": [], "validation": [], "commands": [], "samples": [],
              "scope": "aligned adapter pipeline: native enumeration, semantic projection, policy, checked transitions, per-game clocks and records; setup, final snapshots, and serialization excluded",
              "limits": ["restricted common policy, not unrestricted Splendor", "no-action, profile-blocked and selected multi-noble stops retained",
                         "Rust records are typed; C++ records use JSON boxing inside timing",
                         "AhinLendor uses a direct serial loop; Rust and seal256 use one prepared worker",
                         "C++ move tables are decoded before timing in both adapters",
                         "one shared Mac; intervals describe repetition noise, not other hosts or playing strength"]}

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    def run(engine, corpus, policy, trace=False, label="measure"):
        command = [str(BINARIES[engine]), "--corpus", str(corpus), "--policy", policy, "--threads", "1"]
        if trace:
            command += ["--trace"]
            if engine == "splendorust": command += ["--check"]
        entry = {"engine": engine, "label": label, "command": command,
                 "load_before": os.getloadavg(), "utc": datetime.now(timezone.utc).isoformat()}
        report["commands"].append(entry)
        save()
        start = time.monotonic()
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=600)
            entry.update(exit=result.returncode, process_seconds=time.monotonic() - start, load_after=os.getloadavg())
            if result.returncode:
                stderr.seek(0)
                entry["stderr"] = stderr.read().decode()
                save()
                raise RuntimeError(f"{engine} {label} failed: {entry['stderr']}")
            stdout.seek(0)
            obj = json.load(stdout)
        sample = obj["samples"][0] if engine == "splendorust" else obj
        records = sample.pop("records")
        fields = FIELDS + (["action_keys", "legal_keys", "trace"] if trace else [])
        normalized = [{k: row[k] for k in fields} for row in records]
        count = sample.get("count", sample.get("games"))
        seconds = sample.get("seconds", sample.get("elapsed_seconds"))
        statuses = dict(Counter(r["status"] for r in normalized))
        assert count == len(normalized) == sum(statuses.values())
        assert sample["completed"] == statuses.get("complete", 0)
        assert all((r["status"] == "complete") == r["final_state"]["terminal"] for r in normalized)
        entry["timing_boundary"] = obj["timing_boundary"]
        summary = {"engine": engine, "count": count, "seconds": seconds, "completed": sample["completed"],
                   "turns": sample.get("turns", sample.get("main_turns")), "statuses": statuses,
                   "record_set_sha256": hashlib.sha256(encode(normalized)).hexdigest(), "load": os.getloadavg()}
        save()
        return summary, normalized

    try:
        for name, directory, expected, permitted in (
                ("ahinlendor", "local/strength/external/ahinlendor", "96e6f2daff83147495826c4a2073dc3c9c856cc9", []),
                ("seal256", "local/benchmarks/external/seal256", "263abc066c563a1c89dba4bdc408446a20ad9d1d", ["src/splendor.h"])):
            revision = subprocess.check_output(["git", "-C", str(ROOT / directory), "rev-parse", "HEAD"], text=True).strip()
            dirty = subprocess.check_output(["git", "-C", str(ROOT / directory), "diff", "--name-only"], text=True).splitlines()
            assert revision == expected and dirty == permitted
            report.setdefault("upstream", {})[name] = {"revision": revision, "modified_files": dirty}
        external = {e: json.loads(subprocess.check_output([str(BINARIES[e]), "--export-data"], text=True))
                    for e in ("seal256", "ahinlendor")}
        maps = create(1, 0, external["ahinlendor"])

        def corpus(count, master, name):
            obj = create(count, master, external["seal256"])
            obj["ahin_core_to_native_cards"] = maps["core_to_native_cards"]
            obj["ahin_core_to_native_nobles"] = maps["core_to_native_nobles"]
            path = work / f"{name}.json"
            path.write_bytes(encode(obj))
            return path

        report["data_mapping"] = {"card_tuples_matched": 90, "noble_tuples_matched": 10,
                                  "ahin_core_to_native_cards": maps["core_to_native_cards"],
                                  "ahin_core_to_native_nobles": maps["core_to_native_nobles"]}
        smoke = corpus(1024, 113000001, "trace")
        for policy in ("random", "fixed"):
            reference = None
            for engine in BINARIES:
                sample, records = run(engine, smoke, policy, trace=True, label="trace")
                if reference is None:
                    reference = records
                    archive = out / f"trace-{policy}-records.json.gz"
                    with gzip.open(archive, "wb") as f: f.write(encode(records))
                    report.setdefault("trace_records", {})[policy] = {
                        "file": archive.name, "archive_sha256": sha(archive), "corpus_sha256": sha(smoke)}
                if reference != records:
                    failure = out / f"alignment-failure-{policy}-{engine}.json.gz"
                    with gzip.open(failure, "wb") as f: f.write(encode({"reference": reference, "candidate": records}))
                    raise RuntimeError(f"alignment mismatch: {failure}")
                report["validation"].append({"policy": policy, **sample, "exact_trace_match": True})
                print("trace passed", policy, engine, flush=True)
            save()
        if args.validate_only:
            report["status"] = "validation_only"
        else:
            pilots = corpus(2048, 114000001, "pilot")
            for policy in ("random", "fixed"):
                pilot_samples = [run(e, pilots, policy, label="pilot")[0] for e in BINARIES]
                report["pilots"].extend({"policy": policy, **s} for s in pilot_samples)
                count = min(500000, max(2048, int(max(s["count"] / s["seconds"] for s in pilot_samples) * 2 * 1.15)))
                path = corpus(count, 112000001, policy)
                report.setdefault("corpora", {})[policy] = {"count": count, "master": 112000001,
                                                              "sha256": sha(path), "path": str(path.relative_to(ROOT))}
                save()
                expected_hash = None
                engines = list(BINARIES)
                for repetition in range(7):
                    order = engines[repetition % 3:] + engines[:repetition % 3]
                    if repetition % 2: order.reverse()
                    for engine in order:
                        sample, records = run(engine, path, policy)
                        digest = sample["record_set_sha256"]
                        if expected_hash is None:
                            expected_hash = digest
                            archive = out / f"{policy}-records.json.gz"
                            with gzip.open(archive, "wb") as f: f.write(encode(records))
                            report.setdefault("records", {})[policy] = {"file": archive.name, "archive_sha256": sha(archive)}
                        assert digest == expected_hash, (engine, policy, repetition, "record mismatch")
                        sample.update(policy=policy, repetition=repetition, engine_order=order)
                        report["samples"].append(sample)
                        save()
                        print(policy, engine, repetition, count, round(sample["seconds"], 3), flush=True)
                for engine in engines:
                    rows = [r for r in report["samples"] if r["engine"] == engine and r["policy"] == policy]
                    rates = [r["count"] / r["seconds"] for r in rows]
                    summary = {"trajectories_per_second": statistics.median(rates), "bootstrap95": interval(rates),
                               "completed_games_per_second": statistics.median(r["completed"] / r["seconds"] for r in rows),
                               "complete_turns_per_second": statistics.median(r["turns"] / r["seconds"] for r in rows),
                               "seconds_range": [min(r["seconds"] for r in rows), max(r["seconds"] for r in rows)],
                               "count": count, "statuses": rows[0]["statuses"], "record_set_sha256": expected_hash,
                               "repetitions": len(rows), "confidence": "local repeated timing" if min(r["seconds"] for r in rows) >= 1 else "preliminary"}
                    report.setdefault("summary", {}).setdefault(policy, {})[engine] = summary
                save()
            report["status"] = "complete"
        assert inventory() == report["source_files"], "source changed during run"
        assert {k: sha(p) for k, p in BINARIES.items()} == report["binaries"], "binary changed during run"
        report["source_and_binary_stable"] = True
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["end_utc"] = datetime.now(timezone.utc).isoformat()
        report["machine"]["load_finish"] = os.getloadavg()
        save()


if __name__ == "__main__":
    main()
