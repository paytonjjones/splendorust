# Prepared native checked replay, 2026-10-06

SplendoRust has 23.1–40.1% higher median throughput than pinned AhinLendor on
these four complete two-player traces. Rust is faster in both run orders on
each trace. This result measures checked replay with supplied native moves.
It does not measure policy selection, full legal-list generation, or playing strength.

| Prepared checked replay, one worker, Apple M4 Pro | AhinLendor | **SplendoRust (× AhinLendor)** |
| --- | ---: | ---: |
| Seed 424262 | 851,200 replays/s | **1,067,800 replays/s (1.3×)** |
| Seed 424268 | 928,800 replays/s | **1,143,100 replays/s (1.2×)** |
| Seed 424285 | 769,300 replays/s | **1,075,600 replays/s (1.4×)** |
| Seed 424287 | 851,900 replays/s | **1,193,500 replays/s (1.4×)** |

The table combines 14 repetitions per engine and trace: seven in each order,
with 1,000,000 complete replays per repetition. Rates are rounded to the nearest
100. Multipliers use unrounded medians, then round to one decimal place.
The README abbreviates thousands as `k` and millions as `MM`.
Its single Replay row uses the arithmetic mean of the four trace medians for
each engine. The multiplier is the ratio of those two means.

## Common timing contract

Both engines copy their own initial state at the start of each replay, then
apply every supplied native move through their normal checked entry point.
Action inputs and the state after each complete turn remain observable to
the compiler. State copies and native legality checks remain inside timing.

Trace parsing, move preparation, policy selection, extra legal enumeration,
record creation, state snapshots, and parity checks are outside timing.
Rust receives prepared Actions. C++ receives prepared Moves; token returns
are expanded and noble indices are resolved before timing. The old C++ profile
still performs those conversions during replay and remains available unchanged.

A completed game replay is the comparison unit. The engines use different
native representations and different numbers of internal transitions. C++
combines purchase and automatic colored-first payment. Rust applies purchase
and payment separately. C++ splits a compound colored return into individual
token returns. These fixed traces use the established shared payment/return
scope, not every canonical legal choice. Initial-state copying is included;
these are not isolated transition-operation rates.

## Checks and uncertainty

The original four trace hashes match. Setup, each completed turn, final state,
terminal status, and winners passed the existing parity checks outside timing.
The prepared move counts match the original native replay. Both batches used
identical source and binary hashes, which remained stable within measurement.
The old profiles also passed all four traces in an excluded compatibility run.

| Seed | Turns; Rust/C++ applies | Rust 95% interval, replays/s | C++ 95% interval, replays/s | Rust gain, forward / reverse |
| --- | ---: | ---: | ---: | ---: |
| 424262 | 68; 117/71 | 1,061,665–1,070,077 | 847,509–855,242 | 25.2% / 25.2% |
| 424268 | 64; 113/64 | 1,139,347–1,147,202 | 924,777–935,820 | 22.8% / 23.6% |
| 424285 | 70; 123/76 | 1,069,686–1,078,609 | 762,464–773,889 | 39.7% / 41.2% |
| 424287 | 62; 105/65 | 1,185,064–1,197,007 | 846,564–856,803 | 40.9% / 38.8% |

Rust sample windows range from 0.831 to 0.950 seconds; C++ windows range from
1.063 to 1.319 seconds. Both orders and all samples are retained. The percentile
bootstrap uses 10,000 resamples and seed 20260928. Its intervals describe timing
repetition noise on this shared Apple M4 Pro, not other hosts or other games.

The source change adds a selector to the Rust benchmark example and a new
prepared-native profile to the C++ benchmark. No production engine, agent, rule,
champion, or engine version changed. AhinLendor engine source remains unchanged
at `96e6f2daff83147495826c4a2073dc3c9c856cc9`. The receipts contain exact compilers,
release flags, source and binary hashes, commands, host load, and raw timings.

## Repeat the run

Run from the repository root with the pinned toolchain, Cargo.lock, and the
pinned AhinLendor checkout described in the [earlier build guide](../current-20261006/REPRODUCE.md).
Use a new output directory and run heavy work in sequence.

```sh
python3 research/engine-throughput/run.py local/research/prepared-replay/forward \
  --seeds 424262 424268 424285 424287 --games 1000000 --repeats 7 --prepared-checked-only
python3 research/engine-throughput/run.py local/research/prepared-replay/reverse \
  --seeds 424287 424285 424268 424262 --games 1000000 --repeats 7 --skip-build --prepared-checked-only
python3 research/engine-throughput/summarize_prepared.py local/research/prepared-replay
```

## Evidence

- [Registered plan and budget](PLAN.md).
- [Checked summary](summary.json) and [preview table](PREVIEW.md).
- [Forward receipt](forward/receipt.json) and [reverse receipt](reverse/receipt.json).
- [Compatibility and build receipt](compatibility/receipt.json).
- [Local checks](CHECKS.json): format, strict workspace Clippy, default and
  all-feature release workspace tests, C++ syntax, and Python syntax.

Each run directory contains its raw CSV timings, stderr checks, complete traces,
compiler details, and command logs. Earlier reports remain unchanged. The README
now uses these prepared replay results. GitHub Actions stays disabled.

The README follow-up commits were later combined into the human-edited README
commit. Commit IDs in measurement receipts retain their original values from
before that history change. Source-file hashes, binary hashes, traces, and raw
timings remain the measurement identities.
