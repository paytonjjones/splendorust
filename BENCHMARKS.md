# Performance evidence

The [external benchmark report](benchmarks/REPORT.md) contains the 2026-09-29
cross-engine baseline. Its [protocol](benchmarks/PROTOCOL.md) and
[result files](benchmarks/results/README.md) keep the workload definitions,
repetitions and limits separate from the historical measurements below.

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

## Sparse owned-card scans

The new sampling and invariant fixtures use setup seed 42, random trajectory
seed 123, and hidden-sampling seed 456. Each player-count fixture is measured
at opening and after 40 complete turns. The same pinned toolchain, host, bench
profile, 20 samples, and one-second warm-up/measurement windows were used.
No build or other planned compute workload ran during each measurement.

The prior implementation tested every card ID for every player in both
observation sampling and derived-score validation. The retained implementation
visits only set bits in ascending ID order. It makes no RNG calls and preserves
all validation checks. These checks are outside normal action transitions.

| Hidden-state sample | Before | After |
|---|---:|---:|
| Opening, 2 players | 571.64 ns | 358.57 ns |
| Turn 40, 2 players | 491.18 ns | 320.92 ns |
| Opening, 3 players | 605.19 ns | 361.21 ns |
| Turn 40, 3 players | 555.33 ns | 336.29 ns |
| Opening, 4 players | 632.01 ns | 363.17 ns |
| Turn 40, 4 players | 590.47 ns | 357.54 ns |

Sampling time fell about 35–43% on these fixtures. Invariant-check time fell
about 29–59%. These are one before/after Criterion pair on a shared Mac, not
dedicated-host or cross-platform guarantees. Raw intervals, estimates, source
identifiers, benchmark hash, and settings are in
`docs/results/sparse-owned-benchmarks.json` and the adjacent text logs.

A 1,000-game search/strong comparison (128 iterations, depth 8, width 6,
one thread, master seed 97,000,000) produced identical records and trajectory
hashes before and after. Both runs had 999 normal completions and one blocked
game. This is equivalence evidence, not agent-promotion evidence. The whole-run
times were 30.78 s and 30.08 s; a single pair does not establish an overall
search-speed improvement. Compressed reports retain the incomplete record.

Reproduce the microbenchmark with:

```sh
cargo bench -p splendor-core --bench engine --locked -- \
  'determinize|invariants' --sample-size 20 --warm-up-time 1 \
  --measurement-time 1 --save-baseline before
# With the candidate source:
cargo bench -p splendor-core --bench engine --locked -- \
  'determinize|invariants' --sample-size 20 --warm-up-time 1 \
  --measurement-time 1 --baseline before
```

## Version 2 counter-check measurement

Compared v1 commit `e03b638` (source `ae728260bd1abd30`) with v2 commit
`388243b` (source `5fbacedf05ec987b`) on the same Apple M4 Pro, macOS 26.7,
Rust 1.98.1 / LLVM 22.1.8. Benchmark source, Cargo.lock, toolchain, and profiles
are identical. The core runtime difference is the pre-mutation capacity check
and its error/version declarations. Test-only source changes also affect the
build fingerprint. Both builds finished before timing; runs were serial in
v1, v2, v2, v1, v1, v2 order. This remains a shared-machine measurement.

Each run uses 40 Criterion samples, one-second warm-up and measurement windows.
The table gives medians of the three per-run mean estimates, not a confidence
interval over independent machines.

| Operation | v1 | v2 | Change |
|---|---:|---:|---:|
| Batched opening apply | 25.256 ns | 25.406 ns | +0.6% |
| Opening clone plus apply | 23.694 ns | 23.906 ns | +0.9% |
| Fixed seeded random game | 6.225 µs | 6.139 µs | −1.4% |

These small mixed differences do not justify a performance change. They do not
prove that the guard is free or that all phases have identical performance.
Apply benchmarks use the first opening action. The full-game workload uses two
players, setup seed 42, policy RNG seed 123, and a 10,000-decision limit. It
includes setup and legal generation. This experiment does not measure search
throughput or the counter-limit error path. The separate capacity validation
already established identical records for 1,000 search/strong games.

Raw text logs `docs/results/capacity-[0-5]-v*.txt` and
`docs/results/capacity-benchmarks.json` preserve all estimates and intervals,
source and workload identity, host/compiler details, log hashes, and commands.
Reproduce in separate checkouts at the two stated commits, after compiling both:

```sh
cargo bench --locked -p splendor-core --bench engine --no-run
cargo bench --locked -p splendor-core --bench engine -- \
  '^(clone_apply|apply|random_game)$' --sample-size 40 \
  --warm-up-time 1 --measurement-time 1 --save-baseline capacity-RUN-VERSION
```

## Fixed phase transition baselines

The core benchmark now includes `transition/main-midgame`, `transition/payment`,
`transition/return`, and `transition/noble`. Each fixture and its selected
successor pass full invariants before timing. Criterion creates fresh states
in untimed batch setup; the measured closure applies one action and consumes
the resulting state. No fixture search, validation, formatting, or I/O is in
the measured closure. As with the opening apply benchmark, this is not a
subtraction estimate of an isolated function call.

Main, Payment, and Return use the existing two-player seed-42 trajectory with
policy RNG 123. Noble uses a fixed four-player trajectory: setup seed 9, policy
RNG 123, after 215 decisions. An offline search found that trajectory; the
benchmark itself replays only the fixed prefix and asserts Phase::Noble.
All four select the first generated legal action. The log identifies the
turn, action, and an FNV fingerprint of full starting state/action/successor.

Initial v2 run, same host/toolchain as the counter-check comparison, 40 samples,
one-second warm-up and measurement windows:

| Fixture and selected action | Mean | Criterion 95% mean interval |
|---|---:|---:|
| Turn 31 Main: take three colors | 25.33 ns | 25.20–25.44 ns |
| Turn 8 Payment: zero colored tokens | 26.68 ns | 26.58–26.79 ns |
| Turn 11 Return: two gold tokens | 26.48 ns | 26.09–26.88 ns |
| Turn 138 Noble: choose noble 7 | 22.83 ns | 22.67–23.02 ns |

These are one fixture per phase, not a distribution over all payments, returns,
nobles, end-game states, or player counts. No performance improvement is claimed.
The new benchmark source is outside the production fingerprint; its SHA-256,
source `5fbacedf05ec987b`, fixture identities, and all estimates are recorded in
`docs/results/transition-phases-v2.json`, with the adjacent raw text log.

```sh
cargo bench --locked -p splendor-core --bench engine -- \
  '^transition/' --sample-size 40 --warm-up-time 1 \
  --measurement-time 1 --save-baseline phase-v2
```

## Current v2 search profile

At source `5fbacedf05ec987b`, profiled a fixed release workload with macOS
`sample`: five seconds at one-millisecond intervals, four arena threads,
10,000 search/strong games, seed 112,000,000, 128 iterations, depth 8, width 6.
The build finished before launch. The completed run contains 9,998 normal
completions and two blocked games, with no capped game or invented winner.
Its record/settings structure passes the archive validator. This is diagnostic
sampling, not agent-strength evidence; its 78.24-second elapsed time is not a
clean throughput baseline.

The collapsed top-of-stack list reports 8,622 samples in `potential`, 813 in
`action_score_cached`, 555 in legal generation, 394 in determinization, 173 in
invariant checks, and 112 in action application. Counts combine sampled threads
and can attribute inlined work to callers; they are not exact function timings
or percentages of total wall time. The profile still supports focusing on
heuristic evaluation before core transitions.

Source inspection found that strong Take scoring recalculates the actor's base
potential instead of using the supplied cached value. Visible reservation
scoring already uses that cache. This expression predates the current branch's
work; no recent v2 regression is inferred. E14 in EXPERIMENTS.md records a
score-preserving cache hypothesis and required equivalence/timing checks before
any agent edit.

Evidence: `docs/results/search-v2-profile.json` records settings, source and
record hashes, profiler arguments and process exits. The `.sample.gz` retains
the full sample, `-summary.txt` the collapsed list, and `-report.json.gz` the
complete arena report. The arena exits 1 because two games are blocked; sampling
itself exits 0. Reproduce by launching the recorded arena command, then running
`sample PID 5 1 -file OUTPUT` against that live process.

## Take potential cache (E14)

A serial ABBAAB comparison of 1,000 search/strong games per run at seed 116m,
128 iterations/depth 8/width 6, one thread, reduces median runtime from 29.219
to 23.103 seconds (20.9%; throughput +26.5%). A fresh 1,116m confirmation pair
falls from 29.453 to 23.354 seconds (20.7%). All game records are unchanged;
the confirmation pair preserves one blocked game in each build. These are
clean release runs, without sampling or concurrent test/build work.

Host: Apple M4 Pro, macOS 26.7, Rust 1.98.1, pinned lockfile, release thin LTO
and one codegen unit. Source changes from `5fbacedf05ec987b` to
`0bcb24bf9c705a56`. This is a measured benefit for one workload and host,
not a portable speed guarantee or a strength result. Full timing samples,
commands, reports, source and binary hashes are in
`docs/results/e14-comparison.json` and its referenced archives. See E14 in
EXPERIMENTS.md for the pre-edit hypothesis and score-equivalence test.

### Profile after E14

Repeated the original 10,000-game diagnostic workload at source
`0bcb24bf9c705a56` (112m, 128/8/6, four threads), sampled for five seconds at
1ms. Full records, including trajectory hashes, equal the earlier profile's
records: 9,998 completions and two blocked games, arena exit 1. Sample exit 0.
`potential` remains the largest application top-of-stack entry (9,897 samples),
followed by action_score_cached (1,259), legal generation (807), and
determinization (629). Counts are not comparable wall-time shares between
profiles. Inlining, scheduling and the sampled portion of the workload can
change attribution. Clean E14 timing evidence is separate above.

Raw sample, report, commands, hashes and summary are retained as
`docs/results/e14-profile*`. Source inspection identifies repeated discount,
cost, and card-worth calculations across token-only alternatives. E15 records
a hypothesis to cache those fixed values before any further agent change.

## Fixed target cache (E15)

After E14, cached discounted target costs and card worth reduce serial median
search/strong runtime from 23.554 to 18.662 seconds (20.8%, throughput +26.2%).
Settings: 1,000 games, seed 117m, 128/8/6, one thread, ABBAAB order. Fresh seed
1,117m gives 23.730 to 18.744 seconds (21.0%). Every game completes and full
records, including trajectory hashes, are unchanged within each workload.

Same M4 Pro/macOS 26.7, pinned Rust 1.98.1, Cargo.lock and release profile.
Source `0bcb24bf9c705a56` changes to `50400f40eb161b1a`. No profiler or concurrent
build/test ran during timing. Full evidence is in `docs/results/e15-comparison.json`
and its referenced reports/logs. Do not add the E14 and E15 percentages: the
baselines and seeds differ. No portable speed or playing-strength claim.
