# Benchmarks

Measure engine speed and agent strength separately. Faster state changes do
not prove better play. More search simulations do not mean equal compute.

## Measure speed

Use release builds, the pinned toolchain, and `Cargo.lock`. Keep the host,
seeds, player count, thread count, and workload fixed between builds.

```sh
cargo bench --locked -p splendor-core --bench engine -- --save-baseline before
cargo bench --locked -p splendor-arena --bench arena -- --save-baseline before
```

After one change, run on the same host with the same build settings:

```sh
cargo bench --locked -p splendor-core --bench engine -- --baseline before
cargo bench --locked -p splendor-arena --bench arena -- --baseline before
```

Criterion saves estimates under `target/criterion`. For a broader CLI workload:

```sh
cargo run --release --locked -- benchmark --games 100000 --players 2 --threads 4
```

The core benchmarks measure setup, copies, legal actions, transitions, and
sampled hidden states. Arena benchmarks also include scheduling and reports.
Keep those timing scopes separate.

## Read a speed result

Record the source fingerprint, binary hash, command, seeds, repetitions, CPU,
OS, compiler, build settings, and other work on the host. Build before timing.
Use repeated runs and reverse the build order to check for order effects.

Check behavior outside the timed section. A change that claims identical
behavior must preserve legal choices, outcomes, and game records.

State what the rate counts: complete games, attempted games, decisions, or
transitions. Keep blocked and capped games in the report. A fast stopped game
must not be counted as a complete game.

## Find performance evidence

| Report | Scope |
| --- | --- |
| [Prepared checked replay, 2026-10-06](benchmarks/results/prepared-replay-20261006/REPORT.md) | Native moves prepared before timing; checked complete game replay with AhinLendor on four fixed traces. |
| [Current engine comparison, 2026-10-06](benchmarks/results/current-20261006/REPORT.md) | Aligned random and fixed play with seal256 and AhinLendor, plus a fresh run of the four replay traces. |
| [Canonical engine throughput](research/engine-throughput/RESULTS.md) | Complete Rust decision lists and transitions compared with pinned AhinLendor C++ on four fixed two-player traces. |
| [External engine comparison](benchmarks/REPORT.md) | Earlier cross-engine workloads, with explicit compatible rules and timing limits. |
| [Neural throughput](research/throughput/REPORT.md) | CPU inference and independent-game batching for frozen small models. |
| [Historical local measurements](docs/history/BENCHMARKS.md) | Core operations, arena scaling, profiles, and cache changes. |

The canonical engine comparison measured a 4.8–11.4% median gain over the
predecoded C++ profile in its first passing batch. The reversed-order batch
also passed on all four traces. These are results for those workloads on a
shared Mac. They do not establish a general engine ranking or agent strength.

Use [the external protocol](benchmarks/PROTOCOL.md) to check which operations
and rules can be compared. A supplied-action replay has a different scope
from legal-action generation plus application.

## Measure playing strength

Use [Strategy](STRATEGY.md) to plan a strength test. Keep the model, opponent,
rules, information access, search settings, and final sample size fixed before
final outcomes. Measure complete-game cost to choose a test that can finish.
Cost can limit the schedule; it is not a separate strength rejection rule.

For external opponents, start with
[the strength report](benchmarks/strength/REPORT.md) and
[the native AlphaZero integration](benchmarks/strength/native/INTEGRATION.md).
Keep unsupported choices and unknown outcomes. Do not infer strength from
speed tests or only from games that completed.
