#!/usr/bin/env python3
"""Check both prepared replay orders and save the preview table."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(rates):
    rng = random.Random(20260928)
    medians = sorted(statistics.median(rng.choices(rates, k=len(rates))) for _ in range(10000))
    return [medians[250], medians[9750]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory.resolve()
    suite = json.loads((ROOT / "research/engine-throughput/SUITE.json").read_text())
    batches = [out / "forward", out / "reverse"]
    receipts = [json.loads((p / "receipt.json").read_text()) for p in batches]
    assert receipts[0]["seeds"] == suite["seeds"]
    assert receipts[1]["seeds"] == list(reversed(suite["seeds"]))
    for receipt in receipts:
        assert receipt["profile"] == "prepared_native_checked_apply_only"
        assert receipt["games"] == 1000000 and receipt["repeats"] == 7
        assert receipt["source_stable"] and receipt["binary_stable"] and receipt["all_commands_succeeded"]
    assert receipts[0]["binaries"] == receipts[1]["binaries"]
    assert receipts[0]["source_before"] == receipts[1]["source_before"]
    results = []
    for fixture in suite["rows"]:
        seed = fixture["seed"]
        combined = {"splendorust": [], "ahinlendor": []}
        orders = []
        for batch, receipt in zip(batches, receipts):
            trace = batch / f"seed-{seed}.txt"
            assert sha(trace) == fixture["trace_sha256"]
            assert receipt["outcome_checks"][str(seed)]["matched"]
            lines = trace.read_text().splitlines()
            turns = sum(line.startswith("TURN|") for line in lines)
            actions = sum(line.startswith("ACTION|") for line in lines)
            cpp_log = (batch / f"cpp-{seed}.stderr").read_text()
            assert "exact_full_state_parity=yes prepared_native_moves=yes" in cpp_log
            native = int(re.search(r"native_actions=(\d+)", cpp_log).group(1))
            rates = {}
            for engine, name, column, profile in (
                    ("splendorust", "rust", "workload", "full_checked_apply_only"),
                    ("ahinlendor", "cpp", "profile", "prepared_native_checked_apply_only")):
                with (batch / f"{name}-{seed}.stdout").open() as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 7 and all(r[column] == profile for r in rows)
                assert sorted(int(r["repeat"]) for r in rows) == list(range(7))
                seconds = [float(r["seconds"]) for r in rows]
                assert all(s > 0 for s in seconds)
                if name == "rust":
                    assert all(int(r["replayed_games"]) == 1000000 and
                               int(r["complete_turns"]) == turns * 1000000 and
                               int(r["native_apply_calls"]) == actions * 1000000 and
                               int(r["legal_enumerations"]) == 0 for r in rows)
                else:
                    assert all(int(r["iterations"]) == 1000000 and
                               int(r["operations"]) == native * 1000000 for r in rows)
                combined[engine].extend(seconds)
                rates[engine] = statistics.median(1000000 / s for s in seconds)
            orders.append({"batch": batch.name, "rates": rates,
                           "rust_vs_ahin_ratio": rates["splendorust"] / rates["ahinlendor"]})
        engines = {}
        for engine, seconds in combined.items():
            rates = [1000000 / s for s in seconds]
            engines[engine] = {"replays_per_second": statistics.median(rates),
                               "bootstrap95": interval(rates), "seconds": seconds,
                               "repetitions": len(seconds),
                               "seconds_range": [min(seconds), max(seconds)]}
        results.append({"seed": seed, "trace_sha256": fixture["trace_sha256"],
                        "complete_turns": turns, "rust_applies": actions, "cpp_applies": native,
                        "engines": engines, "orders": orders,
                        "rust_vs_ahin_ratio": engines["splendorust"]["replays_per_second"] / engines["ahinlendor"]["replays_per_second"]})
    summary = {"profile": "prepared_native_checked_apply_only", "games_per_repeat": 1000000,
               "repeats_per_order": 7, "results": results,
               "receipts": {b.name: sha(b / "receipt.json") for b in batches},
               "summary_source_sha256": sha(Path(__file__)),
               "bootstrap": {"resamples": 10000, "seed": 20260928, "coverage": 0.95},
               "scope": "initial-state clone plus native checked moves; move conversion and parity checks outside timing",
               "limits": ["four fixed complete two-player traces on one shared host",
                          "engines perform different numbers of native applies",
                          "C++ automatic colored-first payment and shared return scope remain",
                          "no policy selection or complete legal-list generation",
                          "intervals sample timing repetitions, not different game traces"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    table = ["| Prepared checked replay, one worker, Apple M4 Pro | AhinLendor | **SplendoRust (× AhinLendor)** |",
             "| --- | ---: | ---: |"]
    for result in results:
        rates = {e: round(s["replays_per_second"] / 100) * 100 for e, s in result["engines"].items()}
        table.append(f"| Seed {result['seed']} | {rates['ahinlendor']:,} replays/s | **{rates['splendorust']:,} replays/s ({result['rust_vs_ahin_ratio']:.1f}×)** |")
    (out / "PREVIEW.md").write_text("\n".join(table) + "\n")
    print("\n".join(table))


if __name__ == "__main__":
    main()
