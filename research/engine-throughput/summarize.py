#!/usr/bin/env python3
"""Check the fixed complete trace suite and report medians with explicit units."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]


def summarize(rows, operations, games, turns):
    seconds = [float(row["seconds"]) for row in rows]
    return {
        "repeats": len(rows), "seconds": seconds,
        "median_seconds": statistics.median(seconds),
        "median_games_per_second": games / statistics.median(seconds),
        "median_ns_per_complete_turn": statistics.median(seconds) * 1e9 / (games * turns),
        "median_ns_per_internal_operation": statistics.median(seconds) * 1e9 / (games * operations),
        "internal_operations_per_game": operations,
        "ns_per_complete_turn_range": [min(seconds) * 1e9 / (games * turns), max(seconds) * 1e9 / (games * turns)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    suite = json.loads((ROOT / "research/engine-throughput/SUITE.json").read_text())
    receipt = json.loads((run / "receipt.json").read_text())
    assert receipt["source_stable"] and receipt["binary_stable"] and receipt["all_commands_succeeded"]
    assert receipt["seeds"] in [suite["seeds"], list(reversed(suite["seeds"]))]
    assert receipt["games"] == suite["games_per_repeat"]
    assert receipt["repeats"] == suite["repeats"]
    results = []
    for fixture in suite["rows"]:
        seed = fixture["seed"]
        trace = run / f"seed-{seed}.txt"
        assert hashlib.sha256(trace.read_bytes()).hexdigest() == fixture["trace_sha256"]
        turns = sum(line.startswith("TURN|") for line in trace.read_text().splitlines())
        actions = sum(line.startswith("ACTION|") for line in trace.read_text().splitlines())
        assert receipt["outcome_checks"][str(seed)]["matched"]
        rust_rows = list(csv.DictReader((run / f"rust-{seed}.stdout").open()))
        cpp_rows = list(csv.DictReader((run / f"cpp-{seed}.stdout").open()))
        native = int(re.search(r"native_actions=(\d+)", (run / f"cpp-{seed}.stderr").read_text()).group(1))
        profiles = {}
        for profile in ["full_new_buffer_checked", "full_optimized_enum_checked", "full_optimized_reused_checked", "full_validated_decision"]:
            rows = [r for r in rust_rows if r["workload"] == profile]
            assert len(rows) == suite["repeats"]
            for row in rows:
                assert int(row["replayed_games"]) == receipt["games"]
                assert int(row["complete_turns"]) == turns * receipt["games"]
                assert int(row["native_apply_calls"]) == actions * receipt["games"]
                assert int(row["legal_enumerations"]) == actions * receipt["games"]
            profiles[profile] = summarize(rows, actions, receipt["games"], turns)
        for profile in ["original_full_turn_trace", "predecoded_full_enum_apply"]:
            rows = [r for r in cpp_rows if r["profile"] == profile]
            assert len(rows) == suite["repeats"]
            assert all(int(r["iterations"]) == receipt["games"] and int(r["operations"]) == native * receipt["games"] for r in rows)
            profiles["cpp_" + profile] = summarize(rows, native, receipt["games"], turns)
        baseline_rows = list(csv.DictReader((run / f"baseline-{seed}.stdout").open()))
        assert len(baseline_rows) == suite["repeats"]
        assert all(int(r["replayed_games"]) == receipt["games"] and int(r["native_apply_calls"]) == actions * receipt["games"] for r in baseline_rows)
        profiles["original_rust_7byte_action"] = summarize(baseline_rows, actions, receipt["games"], turns)
        rust_log = (run / f"rust-{seed}.stderr").read_text()
        choices = ast.literal_eval(re.search(r"choices_by_phase=(\[[^\]]+\])", rust_log).group(1))
        max_choices = ast.literal_eval(re.search(r"max_choices_by_phase=(\[[^\]]+\])", rust_log).group(1))
        validated = profiles["full_validated_decision"]["median_seconds"]
        cpp = profiles["cpp_predecoded_full_enum_apply"]["median_seconds"]
        result = {"seed": seed, "turns": turns, "canonical_actions": actions, "cpp_native_applies": native,
                  "legal_choices_by_phase_main_payment_return_noble": choices, "max_choices_by_phase": max_choices,
                  "profiles": profiles, "validated_throughput_ratio_vs_cpp_predecoded": cpp / validated,
                  "validated_speedup_vs_original_rust": profiles["original_rust_7byte_action"]["median_seconds"] / validated}
        results.append(result)
        print(seed, "Rust validated ns/turn", round(profiles["full_validated_decision"]["median_ns_per_complete_turn"], 2),
              "C++ ns/turn", round(profiles["cpp_predecoded_full_enum_apply"]["median_ns_per_complete_turn"], 2), "ratio", round(cpp / validated, 4))
    report = {"scope": "four fixed complete two-player traces; complete canonical Rust lists and phases retained; C++ shared-choice subset",
              "status": "all_trace_medians_match_or_exceed_cpp" if all(r["validated_throughput_ratio_vs_cpp_predecoded"] >= 1 for r in results) else "gap_remains",
              "receipt_sha256": hashlib.sha256((run / "receipt.json").read_bytes()).hexdigest(), "results": results}
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
