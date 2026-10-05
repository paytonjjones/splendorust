#!/usr/bin/env python3
"""Compare real caller costs and exact records without changing agent policies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "local/research/engine-throughput/runtime"
BINS = {"before": ROOT / "local/research/engine-throughput/baseline-target/release/splendor",
        "after": ROOT / "local/research/engine-throughput/target/release/splendor"}


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    OUT = parser.parse_args().output.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    receipt = {"binary_sha256": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in BINS.items()},
               "commands": [], "random_benchmark": {}, "record_comparisons": {}}

    def run(label, binary, args):
        command = [str(binary)] + list(map(str, args))
        start = time.monotonic()
        load = os.getloadavg()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        (OUT / f"{label}.stdout").write_text(result.stdout)
        (OUT / f"{label}.stderr").write_text(result.stderr)
        receipt["commands"].append({"label": label, "command": command, "returncode": result.returncode,
            "wall_seconds": time.monotonic() - start, "load_before": load, "load_after": os.getloadavg()})
        (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return result

    for players in [2, 3, 4]:
        samples = {"before": [], "after": []}
        for repeat in range(3):
            order = ["before", "after"] if repeat % 2 == 0 else ["after", "before"]
            for version in order:
                result = run(f"random-{players}-{version}-{repeat}", BINS[version],
                             ["benchmark", "--games", "12000", "--players", players, "--seed", "87624262", "--threads", "1"])
                assert result.returncode == 0
                counts = re.search(r"core outcomes: (\d+) completed, (\d+) blocked", result.stdout)
                rate = re.search(r"core random: ([\d.]+) games/s, ([\d.]+) decisions/s", result.stdout)
                assert counts and rate
                completed, blocked = map(int, counts.groups())
                samples[version].append({"completed": completed, "blocked": blocked,
                    "attempted_games_per_second": float(rate.group(1)), "decisions_per_second": float(rate.group(2)),
                    "complete_games_per_second": float(rate.group(1)) * completed / 12000})
        assert len({(r["completed"], r["blocked"]) for v in samples.values() for r in v}) == 1
        receipt["random_benchmark"][str(players)] = samples
        print("random", players, "complete-games/s ratio", statistics.median(r["complete_games_per_second"] for r in samples["after"]) /
              statistics.median(r["complete_games_per_second"] for r in samples["before"]), flush=True)

    for policy, games, extra in [("strong", 1000, []), ("search", 64, ["--iterations", "128", "--depth", "8", "--width", "6"])]:
        reports = {}
        for version in ["before", "after"]:
            output = OUT / f"{policy}-{version}.json"
            result = run(f"records-{policy}-{version}", BINS[version], ["compare", "--agent-a", policy, "--agent-b", "greedy" if policy == "strong" else "strong",
                "--games", games, "--seed", "87624262", "--threads", "1", "--output", output] + extra)
            assert output.exists(), result.stderr
            reports[version] = json.loads(output.read_text())
        assert reports["before"]["records"] == reports["after"]["records"]
        assert reports["before"]["engine"] == reports["after"]["engine"]
        receipt["record_comparisons"][policy] = {"games": games, "all_records_identical": True,
            "completed": reports["after"]["completed_games"], "incomplete": reports["after"]["incomplete_games"],
            "before_seconds": reports["before"]["runtime_seconds"], "after_seconds": reports["after"]["runtime_seconds"],
            "records_sha256": hashlib.sha256(json.dumps(reports["after"]["records"], sort_keys=True).encode()).hexdigest()}
        print(policy, "records identical", games, flush=True)
    receipt["binary_after"] = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in BINS.items()}
    assert receipt["binary_after"] == receipt["binary_sha256"]
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
