# External benchmark baseline — 2026-09-29

This report ranks only workloads with checked equivalent behavior. The full
published-rule Splendorust workload remains a native baseline. A restricted
whole-game profile and a checked opening operation permit comparisons with the
public C++ reference. No unrestricted whole-game or cross-engine search speed
claim follows. The C++ repository has no license file; it is a public-source
reference, not a verified licensed open-source implementation.

The protocol is [PROTOCOL.md](PROTOCOL.md). The exact whole-game contract is
[PROFILES.md](PROFILES.md). Pinned candidates, licenses, APIs and failed gates
are in [CANDIDATES.md](CANDIDATES.md). Historical `BENCHMARKS.md` measurements and
all failed experiments remain in place.

## Measured baseline

All rates below are medians of seven repetitions. Brackets give the 95% bootstrap interval for the median rate. Rates count the stated unit; completed-game rates count only normal completions.

Host: Apple M4 Pro, 14 physical/logical cores, 48 GiB memory, macOS 26.7 ARM64, AC power. Rust 1.98.1 / LLVM 22.1.8; Apple Clang 21.0.0; runner Python 3.14.6. The isolated Numba environment uses Python 3.12.7. Rust release uses optimization level 3, thin LTO and one codegen unit. C++ uses `-O3 -DNDEBUG -std=c++17 -pthread` without LTO. No CPU affinity or frequency lock was set. These results are conditional on these builds; paired LTO sensitivity remains unmeasured.

Native measured source: `d93212f22090bea59925e9e7fe5f318169fd5278`. Aligned measured source: `16437bae7beba6777107946967b30ed01457c011`. Both use the same E22 core/agent code and compiled Rust binaries; later source differences are result-checker/documentation changes. The native production fingerprint is `0a98e2c847af1bc7`. Both JSON files retain full suite and binary SHA256 hashes, flags, versions and exact commands.

### Comparable aligned game pipeline

Rank is within each policy and worker count. Both implementations process the identical corpus and outcome/turn totals. This table does not rank unrestricted rules or isolated engine calls.

| Policy | Workers | Rank | Implementation | Attempted trajectories/s [95%] | Completed games/s | Completed turns/s | Timing range (s) |
|---|---:|---:|---|---:|---:|---:|---:|
| random | 1 | 1 | splendorust | 68,476 [68,029–69,400] | 43,608 | 3,804,589 | 4.403–4.634 |
| random | 1 | 2 | seal256 | 36,598 [36,287–37,468] | 23,307 | 2,033,390 | 8.226–8.747 |
| random | 4 | 1 | splendorust | 233,593 [231,695–235,557] | 148,760 | 12,978,562 | 1.320–1.343 |
| random | 4 | 2 | seal256 | 117,735 [116,744–118,271] | 74,978 | 6,541,447 | 2.618–2.665 |
| fixed | 1 | 1 | splendorust | 46,082 [45,662–46,548] | 36,697 | 2,749,429 | 4.384–4.550 |
| fixed | 1 | 2 | seal256 | 28,383 [27,593–29,121] | 22,602 | 1,693,437 | 6.818–7.578 |
| fixed | 4 | 1 | splendorust | 163,431 [157,044–166,806] | 130,146 | 9,751,003 | 1.219–1.402 |
| fixed | 4 | 2 | seal256 | 63,812 [60,724–72,724] | 50,815 | 3,807,271 | 2.600–3.516 |

| Policy | Unique attempted cases per repetition | Complete | Profile blocked | Unsupported noble choice | No legal action |
|---|---:|---:|---:|---:|---:|
| random | 310,969 | 198,035 | 90,730 | 22,131 | 73 |
| fixed | 207,199 | 165,000 | 9,485 | 32,714 | 0 |

Splendorust ranks first against this one C++ reference in the tested profile. Its one-thread median aligned pipeline rate is 1.87× for random play and 1.62× for fixed play. These ratios are conditional on the profile, adapters and host. Random completes 63.7% of attempts; fixed completes 79.6%. Repetitions reuse cases and do not add independent policy samples. All eight windows exceed one second. C++ fixed/four-worker timing varies from 2.600 to 3.516 seconds; its broad interval limits any scaling claim. One-worker comparisons are primary.

### Comparable checked opening operation

| Workers | Rank | Implementation | Checked clone/take transitions/s [95%] | Timing range (s) | Confidence |
|---:|---:|---|---:|---:|---|
| 1 | 1 | splendorust | 57,178,994 [56,631,306–57,418,755] | 5.441–5.518 | local repeated timing |
| 1 | 2 | seal256 | 4,046,324 [3,998,854–4,077,253] | 1.506–1.565 | local repeated timing |
| 4 | 1 | splendorust | 219,554,611 [219,331,206–221,789,662] | 1.408–1.425 | local repeated timing |
| 4 | 2 | seal256 | 8,016,622 [7,748,778–8,413,512] | 0.731–0.851 | preliminary |

Four-worker C++ opening windows are shorter than one second. That row and its ordering are preliminary; no strong four-worker opening ratio is claimed. This operation copies full native state. It does not measure game throughput or isolated apply cost.

### Native Splendorust engine throughput

These full-choice random workloads have no equivalent external adapter. They are unranked. Each pair is **one worker / four workers**, with the same work count and results in both settings.

| Players | Cases per repetition | Complete / blocked / capped | Attempted trajectories/s | Completed games/s | Native decision transitions/s |
|---:|---:|---:|---:|---:|---:|
| 2 | 547,788 | 535,023 / 12,765 / 0 | 100,860 / 383,526 | 98,510 / 374,589 | 11,750,685 / 44,682,583 |
| 3 | 446,055 | 368,890 / 77,165 / 0 | 83,031 / 312,653 | 68,667 / 258,566 | 12,031,808 / 45,305,692 |
| 4 | 305,252 | 264,929 / 40,323 / 0 | 56,369 / 212,198 | 48,923 / 184,168 | 11,388,967 / 42,872,864 |

Native determinism checks use a final public-summary digest plus aggregate counts. They do not retain normalized per-game traces or prove full trajectory equality. The invariant-checked smoke, locked release tests and independent rules-reference checks provide separate correctness evidence.

### Native AI policy and search throughput

These rows include AI selection and opponent work. They have no cross-engine rank. Search is serial within a game; four workers run independent games. Search uses 128 simulations at eligible Main choices, depth eight turns, width six, Strong rollouts and engine evaluation. Search is in seat zero; remaining seats use Strong. Actual simulations are counted. Native decisions include opponents and fallback phases; they are not search invocations.

| Workload | Players | Cases per repetition | Complete / blocked / capped | Games/s (1 / 4 workers) | Native decisions/s (1 / 4) | Actual simulations/s (1 / 4) |
|---|---:|---:|---:|---:|---:|---:|
| greedy | 2 | 146,815 | 146,815 / 0 / 0 | 26,785 / 103,620 | 2,650,607 / 10,254,144 | 0 / 0 |
| search128_strong | 2 | 276 | 276 / 0 / 0 | 53 / 196 | 4,948 / 18,383 | 197,966 / 735,488 |
| search128_strong | 3 | 281 | 281 / 0 / 0 | 52 / 193 | 6,995 / 25,822 | 185,384 / 684,295 |
| search128_strong | 4 | 280 | 280 / 0 / 0 | 52 / 192 | 8,614 / 31,741 | 174,719 / 643,796 |

### Direct per-trajectory latency

The following native probes are separate from throughput timing. Values are microseconds, **one worker / four workers**. Random percentiles pool completed and unfinished cases. Greedy and Search probes completed every case. All probe outcome counts remain in the JSON.

| Native workload | Players | Cases per probe | p50 (µs) | p95 (µs) | p99 (µs) |
|---|---:|---:|---:|---:|---:|
| random | 2 | 1000 | 10.04 / 10.50 | 12.21 / 12.62 | 13.33 / 13.54 |
| random | 3 | 1000 | 13.38 / 14.12 | 15.96 / 16.50 | 17.75 / 17.58 |
| random | 4 | 1000 | 18.88 / 19.96 | 22.17 / 23.08 | 24.08 / 24.71 |
| greedy | 2 | 1000 | 37.62 / 38.50 | 45.08 / 46.04 | 47.54 / 48.54 |
| search128_strong | 2 | 100 | 18,840.21 / 20,178.29 | 21,523.50 / 22,889.88 | 21,973.17 / 23,599.83 |
| search128_strong | 3 | 100 | 19,268.17 / 20,612.04 | 21,100.12 / 22,616.50 | 21,771.00 / 23,228.38 |
| search128_strong | 4 | 100 | 19,272.42 / 20,753.50 | 20,709.21 / 22,176.96 | 21,269.83 / 22,950.62 |

Aligned latency is measured inside the gameplay loop; these are **completed-case** percentiles from the first repetition, in microseconds. Both all-case and unfinished-case distributions are also retained in the JSON.

| Policy | Implementation | Workers | Completed cases | p50 (µs) | p95 (µs) | p99 (µs) |
|---|---|---:|---:|---:|---:|---:|
| random | splendorust | 1 | 198,035 | 17.00 | 21.08 | 23.17 |
| random | splendorust | 4 | 198,035 | 20.25 | 25.25 | 27.75 |
| random | seal256 | 1 | 198,035 | 31.29 | 38.25 | 41.75 |
| random | seal256 | 4 | 198,035 | 38.33 | 46.58 | 50.67 |
| fixed | splendorust | 1 | 165,000 | 22.75 | 24.83 | 26.42 |
| fixed | splendorust | 4 | 165,000 | 25.50 | 28.54 | 29.88 |
| fixed | seal256 | 1 | 165,000 | 34.08 | 37.83 | 40.08 |
| fixed | seal256 | 4 | 165,000 | 66.62 | 73.38 | 76.71 |

### Setup, startup and unranked Python references

| Measurement | Workers | Rate/s [95%] | Scope / limit |
|---|---:|---:|---|
| Splendorust setup | 1 | 4,522,203 [4,514,278–4,526,044] | Full state construction + market observation; local repeated timing |
| Splendorust setup | 4 | 17,586,915 [17,555,530–17,687,976] | Full state construction + market observation; preliminary |
| Numba compiled opening | 1 | 9,794,995 [9,746,122–9,820,093] | Unchecked, independent calibration, no rank or paired scaling claim |
| Numba compiled opening | 4 | 34,395,553 [32,909,261–34,953,278] | Unchecked, independent calibration, no rank or paired scaling claim |
| Numba public-api opening | 1 | 752,823 [746,159–756,896] | Unchecked, independent calibration, no rank or paired scaling claim |

Observed native worker launch/readiness costs were 0.388s (one worker) and 0.014s (four). These are process observations with different cache histories, not intrinsic startup constants. They are excluded from throughput. Setup/four-worker has 0.621–0.627s windows and remains preliminary.

| Aligned policy / implementation | Median serial corpus setup (s), 1 / 4 workers | Median process wall time (s), 1 / 4 |
|---|---:|---:|
| random / splendorust | 0.120 / 0.120 | 7.026 / 3.818 |
| random / seal256 | 0.724 / 0.722 | 14.022 / 8.243 |
| fixed / splendorust | 0.080 / 0.081 | 6.120 / 2.880 |
| fixed / seal256 | 0.498 / 0.504 | 11.121 / 6.860 |

Process wall time includes parsing, warm-up, setup, gameplay, snapshots and serialization; it is not a steady-state engine rate. Python initialization/JIT observations were compiled/t1: 8.366s, compiled/t4: 8.088s, public-api/t1: 8.583s. Cached setup/build step costs and prior setup histories are retained in both baseline JSON files; no cold-install cost is inferred.

### Evidence and reproduction

[Native results](results/native-20260929.json), [aligned results](results/aligned-20260929.json), [result validation](results/check-20260929.json), [build validation](results/build-validation-20260929.json), and the [SHA256 index](results/index-20260929.json) retain raw samples, metadata and record archives. All 31 result rows pass the saved evidence checks; two short native rows remain preliminary. Each common group has a separate rank. No other candidate has a speed rank.

Successfully measured engines are Splendorust, seal256 (checked opening and aligned profile), and lyquentxy (unranked unchecked opening/public API references). Installed but unranked rule probes and source-only references remain in the candidate inventory.

```sh
python3 benchmarks/setup.py --python --references
python3 benchmarks/run.py --output benchmarks/results/native-reproduction.json
python3 benchmarks/run_aligned.py --output benchmarks/results/aligned-reproduction.json --max-cases 400000
python3 benchmarks/check_results.py benchmarks/results/native-reproduction.json benchmarks/results/aligned-reproduction.json
```

Use a new output name for a reproduction so the checked-in baseline stays intact. Regenerate each shared corpus with the recorded master seed `950000001`, count and `make_corpus.py`; canonical output bytes reproduce its hash. Rerun timings sequentially on an idle measurement host.


## Scope and correctness

The `seal256-intersection-v1` profile injects the same full decks and nobles,
uses functional card/noble mappings, and sorts semantic action keys. Random
selection uses the same rejection-sampled SplitMix64 stream. The fixed policy
has the same buy/take/reserve priorities. Both engines validate selected moves.
The profile has two players and the normal 15-point equal-round finish.

The profile excludes blind reservations, partial exhausted-bank takes and token
returns. It retains the C++ double-take omission at eight held tokens and uses
colored-first payment. A selected purchase with multiple eligible nobles stops
as unsupported. Empty profile choices stop without a fabricated pass or winner.
These restrictions align the measured trajectories; they do not establish all
legal-choice equivalence. Every incomplete case remains in the time denominator.

The smoke gate compares every normalized public state, projected legal-action
set, selected key and outcome for 64 random and 64 fixed cases. Larger timed
corpora compare all normalized final records across engines, worker counts and
repetitions. Full hidden deck order is injected once; it is not independently
compared at each turn. Final-record equality is weaker than a full trace gate on
all measured cases. The report retains both gate scope and record hashes.

Aligned throughput includes native legal generation, profile projection, sorting,
policy, checked transitions, per-game clocks and small result records. It excludes
setup, warm-up, pool startup, final snapshots and serialization. C++ uses minimal
JSON record boxing; Rust uses typed records. That difference is retained and
limits the claim to aligned adapter pipeline throughput. It does not isolate
engine apply or enumeration costs. Native phase counts differ, so common completed
player turns are the comparison unit.

The opening group measures full native state clone, checked white/blue/green take,
result consumption and destruction. It excludes legal enumeration and setup.
Native state sizes and clone ownership differ. Rust uses a persistent Rayon pool;
C++ excludes warmed thread creation but includes release/join. One-thread results
are the primary comparison. Opening speed does not imply complete-game speed.

## Rules alignment and policy repairs

The merged three-player fix is PR [#1](https://github.com/paytonjjones/splendorust/pull/1).
The two-player fix changes Search and Strong choices using public sufficient
conditions. It fixes four retained blocked histories and preserves unknown blind
reservations. Core rules, legal actions, RNG and replay behavior remain version 2.
Search rollouts keep their original scoring. An independent review also checked
last-seat noble completion before accepting the final guard.

The fresh E21 screen and confirmation gates contain 70,000 completed Search/Strong
games across two, three and four players, with fixed 128/8/6 budgets. E22 corrects
the last-seat noble boundary. Its same-seed reruns check that all ordered records
remain unchanged; these reruns are not fresh holdouts. The baseline uses the
corrected E22 source. These gates
are conditional on their policies and seeds; they do not prove termination for
all legal play. [Policy evidence](../docs/results/two-player-policy/README.md)
includes the rejected E20 candidate, full reports and regression histories.

A separate Search32 self-play diagnostic has 293/300 completed two-player games,
298/300 three-player games and 298/300 four-player games. Seven two-player cases
reach a verified four-decision token cycle. Four other cases block due to a blind
reservation, a purchase outside the take guard or a sole legal take. All eleven
unfinished histories have no winner. They remain documented references. The
primary search workload uses Search128 in seat zero against Strong in other seats.
It records actual simulations and includes opponent and fallback decisions.
Native greedy includes deterministic local scoring and Observation costs. It is
an AI-policy baseline, distinct from common aligned fixed-policy throughput.
Native random play uses uniform legal choices without AI evaluation or search.

Optional `benchmark-compat` APIs inject complete validated setups and expose an
explicit experimental no-action pass. The measured profile does not use that pass.
It cannot pass when a published legal action exists; a full no-action cycle cannot
produce a stalemate winner. Normal rules and replays remain unchanged. Reports
using this hook must name `splendorust-v2-benchmark-compat-v1` and their exact profile.

## Confidence, references and remaining gaps

Each baseline row retains every repetition and an interval for the median timing
rate from 10,000 deterministic bootstrap samples. These intervals describe local
repetition noise, not game-rule validity, policy strength or performance on other
hardware. Short windows retain a preliminary label. No core affinity, frequency
lock or dedicated host was used. macOS uses a mix of performance and efficiency
cores; background work and scheduling can change rates and scaling.

Native per-game latency comes from a separate instrumented probe. It includes
setup and play but excludes queue wait, final digest and destruction. Its random
latency percentiles pool completed and unfinished trajectories; they are not
completed-game percentiles. Aligned latency clocks are inside the pipeline and
are split by completion status. Batch time divided by game count is not a latency
percentile. Installation/build costs may reuse caches and are not cold-install
estimates. Process wall time includes work excluded from steady-state clocks.

The Numba opening reference verifies fixture results but its timed apply helper
is unchecked. Compiled one/four-thread and public Python API measurements stay
unranked. Their iteration counts are independently calibrated, so no paired
thread-scaling claim is supported. Import, JIT and startup costs are separate. Upstream decorators retain
their pinned optimization flags. Roeey's tiny trace prefixes match, but its
seven-bonus cap and mandatory copied action history exclude a speed ranking.
Splendimax and Go build; concrete transition/rule defects exclude them. Lapidary
has different rules and hidden-information access. The original AlphaZero source
was audited without a runtime measurement. Java and JavaScript references have
standard-card data mismatches. Unsupported results are not zero-throughput rows.

The largest gap is a licensed second implementation with equivalent unrestricted
legal choices, complete setup injection and retained whole-game traces. There is
also no cross-engine search comparison: MCTS, root UCB and depth search perform
different work, even at equal iteration counts. Multihost timings, larger full
trace gates and isolated checked-transition corpora are still needed.

The next benchmark step is to extend the licensed Numba engine's adapter with
verified full fixture conversion, projected choices, explicit unsupported/pre-cap
stops and a checked transition interface. The feasibility probe already verifies
all ninety scheduled native draws without a source patch. Then verify a named
whole-game profile. Keep any upstream interface patch minimal
and recorded. Separately, add late-game checked fixtures for payment, returns,
reservations and nobles. Those fixtures can identify which engine operations
need engineering work before making a broader speed claim.
