# Current engine comparison, 2026-10-06

SplendoRust is faster than both C++ engines on the two aligned workloads.
AhinLendor is faster than seal256: 1.62 times for random play and 1.49 times
for fixed play. SplendoRust is about 2.33 times as fast as AhinLendor on both.
These results apply to the common profile and adapter pipeline below.

The fresh replay run also places SplendoRust above AhinLendor on all four
fixed traces, in both run orders. Its combined median gain is 4.5–16.9%.
These speed tests do not establish a general engine ranking or playing strength.

## Aligned play

| Policy | SplendoRust attempts/s | seal256 attempts/s | AhinLendor attempts/s |
| --- | ---: | ---: | ---: |
| Random | 135,477 | 35,940 | 58,102 |
| Fixed | 101,852 | 29,451 | 43,960 |

Rates are medians of seven repetitions, with one worker on an Apple M4 Pro.
Each repetition uses the same frozen cases in all three engines. Engine order
rotates and reverses. Excluded 2,048-case pilots set the case count before timing.
The measurement master seed is 112000001; the trace-check master is 113000001.

| Policy | Engine | 95% bootstrap interval, attempts/s | Complete games/s | Timed seconds, min–max |
| --- | --- | ---: | ---: | ---: |
| Random | splendorust | 130,341–135,842 | 86,193 | 2.093–2.215 |
| Random | seal256 | 35,402–36,434 | 22,866 | 7.836–8.088 |
| Random | ahinlendor | 56,797–58,758 | 36,965 | 4.858–5.476 |
| Fixed | splendorust | 100,720–102,171 | 81,023 | 2.182–2.469 |
| Fixed | seal256 | 29,141–29,640 | 23,428 | 7.558–7.837 |
| Fixed | ahinlendor | 43,765–44,438 | 34,970 | 5.070–5.432 |

Every attempted game remains in the numerator and timing. Complete-game rates
count only completed games, with time from all attempts. Stop counts match in
all three engines and every repetition:

| Policy | Attempts | Complete | Profile blocked | Unsupported noble choice | No legal action | Decision limit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 286,102 | 182,022 | 83,493 | 20,536 | 51 | 0 |
| Fixed | 225,717 | 179,558 | 10,463 | 35,696 | 0 | 0 |

The workload uses [seal256-intersection-v1](../../PROFILES.md). It excludes
blind reservations, token returns, partial token takes, and alternate payment
choices. A selected purchase with several eligible nobles stops as unsupported.
The adapters preserve seal256’s stricter token-take boundary. No production
rule or legal choice was changed. This is not an unrestricted Splendor test.

Before timing, all 90 card and 10 noble tuples matched. On 1,024 cases per
policy, all three engines produced the same projected legal lists, selected
actions, setup and turn snapshots, final states, and stop reasons. All timed
record-set hashes also matched. Snapshots contain bank and player tokens,
bonuses, scores, reservations, market, remaining deck counts, nobles, current
player, turns, and terminal status. They do not compare the full hidden deck,
purchased-card identities, or winners. This check does not prove general rules parity.

Timing includes native enumeration, projection to common action keys, policy
selection, checked transitions, per-game clocks, and minimal records. It excludes
state setup, final snapshots, and JSON serialization. Rust records are typed;
both C++ adapters construct JSON records inside timing. AhinLendor uses a direct
serial loop; Rust and seal256 use one prepared worker. C++ move tables are
decoded before timing. These are adapter-pipeline rates, not isolated core costs.

AhinLendor had no aligned worker in the earlier report. The new
[adapter](../../adapters/ahin_aligned.cpp) uses its native legal mask and checked
`applyMove`, with the same injected decks, semantic action keys, and policies.

## Complete-turn replay

| Seed | SplendoRust replays/s | AhinLendor replays/s | Rust gain | Gain, forward / reverse |
| --- | ---: | ---: | ---: | ---: |
| 424262 | 447,694 | 404,891 | 10.6% | 9.9% / 9.4% |
| 424268 | 474,069 | 453,676 | 4.5% | 4.5% / 4.7% |
| 424285 | 400,614 | 378,340 | 5.9% | 3.8% / 6.3% |
| 424287 | 503,888 | 431,030 | 16.9% | 18.6% / 16.6% |

Each trace has seven repetitions of 100,000 replays in each of two batches.
The second batch reverses trace and engine order. The table combines all 14
rates per engine. The README rounds replay rates to the nearest 100.

Rust uses `full_validated_decision`: complete canonical lists, membership checks,
and all internal payment, return, and noble decisions. AhinLendor uses
`predecoded_full_enum_apply`: native masks and checked transitions on the shared
trace, with moves decoded before timing. C++ uses automatic colored-first payment
and a shared-choice subset. Complete turns are the comparison unit; the engines
perform different numbers of internal applies. See the
[original replay scope](../../../research/engine-throughput/RESULTS.md).

All four original trace hashes, turn counts, operation counts, state parity
checks, and outcome checks passed in both batches. Sources and binaries stayed
unchanged. seal256 was not measured on these replay traces.

The headline replay windows are about 0.2–0.3 seconds. Both orders and every
sample are retained. Intervals describe repetition noise on one shared host;
they do not cover other machines or all effects of shared-host load. Do not
interpret a change from the earlier report as a separately measured speedup.

## Source and evidence

The production source is main at `6aa20663fb9077fb4598655c656af8f0a1512086`. Only benchmark
adapters, reporting tools, and documentation were added for this comparison.
The build uses Rust 1.98.1, `Cargo.lock`, release mode, and Apple clang. C++ uses
`-O3 -DNDEBUG -std=c++17`; AhinLendor also uses `-flto`, and seal256 uses
`-pthread`. The exact compiler versions, OS, host load, commands, source files,
binary hashes, and timing boundaries are in the receipts.

- AhinLendor: `96e6f2daff83147495826c4a2073dc3c9c856cc9`, unchanged engine source.
- seal256: `263abc066c563a1c89dba4bdc408446a20ad9d1d`, with an interface-only
  header change that exposes its unchanged validation method.
- [Plan and resource budget](PLAN.md).
- [Build receipt](build.json) and [aligned receipt](aligned.json).
- [Checked summary and intervals](summary.json).
- [Local checks and data hashes](checks.json): syntax checks, malformed-input
  rejection, documentation links, and exact README preservation outside the table.
- [Forward replay receipt](replay-forward/receipt.json) and
  [reverse replay receipt](replay-reverse/receipt.json).
- [Commands to repeat the comparison](REPRODUCE.md).

Earlier reports remain unchanged. No Rust production code, agent, champion,
rule, or engine version changed. GitHub Actions stays disabled.
