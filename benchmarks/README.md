# External benchmark suite

Read [PROTOCOL.md](PROTOCOL.md), [PROFILES.md](PROFILES.md), and [REPORT.md](REPORT.md).
The report separates common profile results, native base-game results, and unchecked
API references. Existing `BENCHMARKS.md` results are preserved.

From the repository root, on the measurement host:

```sh
python3 benchmarks/setup.py --python --references
python3 benchmarks/run.py --output benchmarks/results/native.json
python3 benchmarks/run_aligned.py --output benchmarks/results/aligned.json
```

Run these steps in order. Do not build or run another workload during measurement.
The setup command clones pinned sources into ignored `local/benchmarks/external`,
records setup/build cost, and builds optimized adapters. Python uses an isolated
3.12.7 environment with pinned NumPy, Numba, llvmlite and colorama. `uv` is required
for that optional environment. Go reference setup is currently for macOS ARM64.
No UI, neural model, training framework, or network work runs inside the benchmark.

Both runners default to seven repetitions and a 1.25-second pilot target. The
aligned runner caps its corpus at 100,000 cases. Each result states actual duration
and marks shorter windows preliminary. For a smoke run, select two repetitions,
`--target-seconds 0.03`, and for the aligned runner `--max-cases 1024`. Smoke rates
are not baseline evidence.

Native measurements cover 2/3/4-player random play, deterministic greedy play,
32-simulation search, setup, and checked opening copy/take at one and four workers.
Python compiled one/four-thread and public Python API timings remain unchecked
references. The C++ opening adapter has a small access-only patch that exposes its
unchanged native validator; the patch is retained in `external/`.

The whole-game profile accepts the same full deck/noble corpus in both engines.
It restricts policy choices and records unsupported branches. It measures gameplay
from prepared states. Setup, warm-up, pool startup, final snapshots and serialization
are separate. Validate full per-turn states, semantic legal lists and chosen actions
before the long run. Every timed game has a retained final-state record; identical
record-set hashes must match across engines, threads and repetitions.

`benchmark-compat` is optional. Build the aligned Rust interface with:

```sh
cargo build --release --locked -p splendor-arena --examples --features benchmark-compat
```

Core APIs `new_benchmark_setup` and `apply_no_action_pass` are available only with
that feature. Normal legal actions and replay version stay unchanged. The explicit
pass is for a named experimental profile and is not used by the measured
`seal256-intersection-v1` profile. It cannot pass when a published legal action exists.
The published profile continues to report blocked positions without a winner.

`make_corpus.py` verifies all card/noble functional tuples and generates shared
setups from a documented SplitMix64 schedule. The checked-in 64-case fixture is the
trace smoke corpus. Larger corpora can be regenerated from the result's seed/count.
`run_aligned.py` retains compressed per-game records and raw repetition summaries.
The machine-readable result files include hardware, versions, flags, source and
corpus hashes, outcome counts, timing scope, latency and uncertainty.

Source-only references and engines rejected by rule checks remain in `external/`.
Their setup commands and failure reasons are retained; they have no speed rank.
A Numba draw-interface feasibility probe is available, but it is not a full-game
parity or throughput result.
