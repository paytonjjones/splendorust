#!/usr/bin/env python3
"""Check both replay orders and summarize the current engine comparison."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics

from run import interval

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory
    aligned = json.loads((out / "aligned.json").read_text())
    assert aligned["status"] == "complete" and aligned["source_and_binary_stable"]
    assert len(aligned["samples"]) == 42 and len(aligned["validation"]) == 6
    for policy, record in aligned["records"].items():
        assert sha(out / record["file"]) == record["archive_sha256"]
        assert len({r["record_set_sha256"] for r in aligned["samples"] if r["policy"] == policy}) == 1
    for record in aligned["trace_records"].values():
        assert sha(out / record["file"]) == record["archive_sha256"]
    suite = json.loads((ROOT / "research/engine-throughput/SUITE.json").read_text())
    batches = [out / "replay-forward", out / "replay-reverse"]
    receipts = [json.loads((b / "receipt.json").read_text()) for b in batches]
    assert receipts[0]["seeds"] == suite["seeds"]
    assert receipts[1]["seeds"] == list(reversed(suite["seeds"]))
    for receipt in receipts:
        assert receipt["source_stable"] and receipt["binary_stable"] and receipt["all_commands_succeeded"]
        assert receipt["games"] == suite["games_per_repeat"] and receipt["repeats"] == suite["repeats"]
    assert receipts[0]["source_before"] == receipts[1]["source_before"]
    assert receipts[0]["binaries"] == receipts[1]["binaries"]
    # The aligned and replay runs must use identical production Rust sources.
    for path, digest in aligned["source_files"].items():
        if path.startswith("crates/") or path in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml"):
            assert receipts[0]["source_before"][path] == digest
    replay = []
    for fixture in suite["rows"]:
        seed = fixture["seed"]
        timings = {"splendorust": [], "ahinlendor": []}
        order_medians = []
        for batch, receipt in zip(batches, receipts):
            trace = batch / f"seed-{seed}.txt"
            assert sha(trace) == fixture["trace_sha256"]
            assert receipt["outcome_checks"][str(seed)]["matched"]
            turns = sum(line.startswith("TURN|") for line in trace.read_text().splitlines())
            actions = sum(line.startswith("ACTION|") for line in trace.read_text().splitlines())
            with (batch / f"rust-{seed}.stdout").open() as f:
                rust = [r for r in csv.DictReader(f) if r["workload"] == "full_validated_decision"]
            with (batch / f"cpp-{seed}.stdout").open() as f:
                cpp = [r for r in csv.DictReader(f) if r["profile"] == "predecoded_full_enum_apply"]
            native = int(re.search(r"native_actions=(\d+)",
                                  (batch / f"cpp-{seed}.stderr").read_text()).group(1))
            assert len(rust) == len(cpp) == suite["repeats"]
            assert all(int(r["replayed_games"]) == receipt["games"] and
                       int(r["complete_turns"]) == turns * receipt["games"] and
                       int(r["native_apply_calls"]) == actions * receipt["games"] and
                       int(r["legal_enumerations"]) == actions * receipt["games"] for r in rust)
            assert all(int(r["iterations"]) == receipt["games"] and
                       int(r["operations"]) == native * receipt["games"] for r in cpp)
            medians = {}
            for engine, rows in (("splendorust", rust), ("ahinlendor", cpp)):
                seconds = [float(r["seconds"]) for r in rows]
                timings[engine].extend(seconds)
                medians[engine] = receipt["games"] / statistics.median(seconds)
            order_medians.append({"batch": batch.name, "rates": medians})
        result = {"seed": seed, "trace_sha256": fixture["trace_sha256"], "turns": turns,
                  "canonical_actions": actions, "cpp_native_applies": native,
                  "games_per_repeat": suite["games_per_repeat"],
                  "order_medians": order_medians, "engines": {}}
        for engine, seconds in timings.items():
            rates = [suite["games_per_repeat"] / s for s in seconds]
            result["engines"][engine] = {"replays_per_second": statistics.median(rates),
                                         "bootstrap95": interval(rates), "seconds": seconds,
                                         "repetitions": len(seconds)}
        result["rust_vs_ahin_ratio"] = result["engines"]["splendorust"]["replays_per_second"] / result["engines"]["ahinlendor"]["replays_per_second"]
        replay.append(result)
    summary = {"aligned": aligned["summary"], "replay": replay,
               "aligned_receipt_sha256": sha(out / "aligned.json"),
               "replay_receipt_sha256": {b.name: sha(b / "receipt.json") for b in batches},
               "limits": ["one shared host; bootstrap intervals describe repetition noise",
                          "replay windows are short; both run orders are retained",
                          "aligned play is a restricted common profile, not full-rule speed",
                          "replay checks four fixed traces, not policy-driven game performance"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"aligned": summary["aligned"], "replay": replay}, indent=2))


if __name__ == "__main__":
    main()
