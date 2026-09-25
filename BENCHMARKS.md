# Performance evidence

Measured on 2026-09-25: Apple M4 Pro, macOS 26.7, aarch64, Rust 1.98.1, LLVM 22.1.8. Release uses thin LTO and one codegen unit. Criterion adds debug symbols. These are local measurements, not portable performance guarantees.

## Core

Criterion, 20 samples, one-second warm-up and measurement windows:

| Operation | Central estimate | Reported interval |
|---|---:|---:|
| Opening legal actions | 42.35 ns | 41.57–43.09 ns |
| Clone 352-byte state | 12.15 ns | 12.11–12.20 ns |
| Clone plus apply | 24.58 ns | 24.34–24.90 ns |
| Batched action application | 25.88 ns | 25.71–26.06 ns |
| Full seeded random game | 6.78 µs | 6.76–6.82 µs |

Action size is seven bytes on this target. The application benchmark uses fresh batched states and includes moving/consuming its result; it is not a subtraction estimate of one function call. The random-game microbenchmark uses a fixed seed and includes setup. The CLI throughput run covers many seeds and is more representative. New phase-specific benchmarks cover midgame main actions, payments, and token returns; their exact output is in `docs/results/criterion-phases.txt`.

A 100,000-trajectory CLI run measured about **97,940 core trajectories/s**, or **11.39 million decision transitions/s**. It reached 97,517 normal completions and 2,483 blocked states. The throughput numerator includes both and is not advertised as 100,000 completed games. Counting completed games alone gives about 95,508 completions/s for that run.

The isolated opening microbenchmark varies with compiler inlining and run conditions. Prefer repeated Criterion baselines to a single CLI nanosecond estimate. The small change in core timings between the initial and final run is not attributed to the agent cache.

## Arena

100,000 paired random trajectories, setup seed 12,345:

| Arena threads | Trajectories/s | Decision transitions/s |
|---|---:|---:|
| 1 | 82,543 | 9.61 million |
| 4 | 297,550 | 34.65 million |

Both runs produced 97,640 normal completions and 2,360 blocked cases, with the same outcome totals. The arena uses a different documented seed schedule from the direct core throughput loop. This explains the different blocked counts. Invariant checks were disabled for these speed measurements. The separate million-trajectory audit enabled them after every decision.

Criterion's 256-game arena batches measured 2.936 ms with one thread and 0.856 ms with four threads. These batches include thread-pool creation and report assembly, so they should not be compared directly with steady-state core transition timings.

## Profile and retained optimization

A five-second macOS `sample` capture of search showed that repeated card-potential evaluation dominated active CPU samples. Its reduced summary is in `docs/results/profile-summary.txt`. The next largest measured components were action scoring, hidden-state reconstruction, and legal generation. State application was a small part of this search workload.

We cached the common base potential once per decision and cached root scores before sorting. Three alternating before/after runs used the same 1,000-game seed set, one thread, 32 simulations, depth eight, and strong rollouts:

| Version | Median time | Median-derived rate |
|---|---:|---:|
| Before cache | 10.171 s | 98.32 games/s |
| After cache | 8.128 s | 123.03 games/s |

The median elapsed time fell **20.1%** (about **25.1%** more games/s). Every per-game record matched across all six runs. One timing repetition overlapped a short build; this is local evidence with ordinary machine noise, not a dedicated-host performance study. All three after times were lower than all three before times. Together with the profile and unchanged decisions, this supports retaining the cache. The raw timings are in `docs/results/cache-timings.json`.

A further 20,000 strong/greedy games and 1,000 search/strong games also matched every trajectory before and after caching. No apply/undo implementation is justified by the current 12 ns clone cost. Further performance work should focus first on rollout evaluation, then hidden-state sampling if a new profile supports it.

## Reproduce and compare

```sh
cargo bench -p splendor-core --bench engine -- --save-baseline before
cargo bench -p splendor-arena --bench arena -- --save-baseline before
# After one change, on the same host and build configuration:
cargo bench -p splendor-core --bench engine -- --baseline before
cargo bench -p splendor-arena --bench arena -- --baseline before
cargo run --release -- benchmark --games 100000 --threads 4
```

Criterion stores machine-readable estimates below `target/criterion`. Checked-in text reports preserve this run's evidence. Record CPU, OS, compiler, source fingerprint, seeds, sample size, thread count, and concurrent work when comparing future results. Avoid timing regression gates on shared CI runners; use the promotion script's explicit throughput floor on a controlled host when required.
