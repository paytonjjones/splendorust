# Splendorust

A deterministic Rust engine and experiment framework for base Splendor, with 2–4 players. There is no GUI, artwork, network service, or model dependency.

The workspace contains the full 90-card and 10-noble datasets, rule tests, random-play audits, hidden-information-safe agents, paired tournaments, replay, benchmarks, and a promotion gate. Read [VALIDATION.md](VALIDATION.md) before treating results as ground truth. In particular, the published rules leave some no-action positions unresolved; the engine reports these positions without inventing a winner.

The [external benchmark report](benchmarks/REPORT.md) contains the reproducible
baseline, workload rankings and limits. Its [protocol](benchmarks/PROTOCOL.md)
defines the comparable rules and timing scopes.

## Run

Install Rust through rustup. The repository pins Rust 1.98.1. Dependencies are locked in `Cargo.lock`.

```sh
cargo test --workspace --release --locked
cargo run --release -- play --agents strong,greedy --seed 42 --check --output game.json
cargo run --release -- replay game.json
cargo run --release -- compare --agent-a strong --agent-b greedy --games 20000 --seed 9000001 --threads 4 --output comparison.json
cargo run --release -- verify-report comparison.json
cargo run --release -- compare --agent-a search --agent-b strong --games 1000 --seed 100001 --threads 4 --iterations 128 --depth 8
cargo run --release -- tournament --agents strong,greedy,random --games 3000 --threads 4
cargo run --release -- benchmark --games 10000 --players 2 --threads 4
cargo run --release -- audit --games 1000002 --threads 4
```

`games` must be divisible by the player count. Each setup is played in all seat rotations. `compare` puts one candidate against N−1 copies of the baseline. `tournament` accepts 2–4 named identities. A repeated agent name still has a separate RNG stream per identity.

Use `--help` on any command. `play --trace` prints all decisions. `--check` enables state audits after each decision. JSON reports contain ordered per-game records and trajectory hashes. The source fingerprint identifies uncommitted experiments too. Timing fields vary between runs; fixed-budget game records do not depend on thread count. New reports also store structured run settings. `verify-report` reruns these settings and compares every game record, including blocked and capped games. It requires the same source fingerprint and engine version, and rejects timed runs. It does not check timing fields or statistical summaries. Older reports remain readable, but cannot use this command because their settings are not structured.

## Agents

| Name | Policy |
|---|---|
| `random` | Uniform choice from the legal actions at each decision phase |
| `greedy` / `simple-greedy` | Buy affordable cards; favor points and useful bonuses |
| `strong` / `strong-heuristic` | Favor efficient purchases, near-term targets, and noble progress |
| `search` | Root UCB Monte Carlo search with a fresh hidden-state sample per simulation |

`mcts` is a CLI alias for `search`, **not** a claim that this implementation has a persistent MCTS tree. The current search is a simple measured baseline.

Search checks public bank supply and affordable cards before choosing a take
with three reservations. When a take can preserve a legal next turn, it
excludes takes that fail this sufficient bound. This prevents the E18
three-player block without changing the core game rules. It does not guarantee
that all legal policies or all games terminate. See E18 and E19 in
[EXPERIMENTS.md](EXPERIMENTS.md) for fixed-budget strength and completion results
against strong opponents.

Search options: `--iterations`, `--depth` (completed player turns), `--width`, `--rollout random|greedy|strong`, and `--evaluation score|engine`. Fixed iterations are the default. `--search-ms` adds a soft wall-clock cap and marks the report as non-reproducible. A simulation can run past the time cap. Saved action histories still replay exactly.

## Experiment workflow

```sh
python3 scripts/promote.py --candidate strong --baseline greedy --seed 12345 --output results/promotion-new
cargo bench -p splendor-core --bench engine -- --save-baseline before
# Make one measured change, then:
cargo bench -p splendor-core --bench engine -- --baseline before
cargo bench -p splendor-arena --bench arena
```

The gate runs checks, a throughput smoke test, a 2,000-game screen, and a 20,000-game confirmation on disjoint seeds. It requires a new output directory, records parameters in `run.json`, and writes `decision.json`. It rejects unfinished games and can enforce a throughput floor. It uses the executable reported by Cargo, including custom target directories, and records its path and SHA-256 in `build.json` beside `cargo-build.jsonl`. It does not edit source, revert work, or publish anything. For three players, select counts divisible by three. A fresh confirmation seed range is required for each new candidate; repeated use of one holdout does not remain a valid holdout.

CI also runs the pinned independent-reference comparison on six fixed games, checking every visited action set and retaining reference state across shared turns. See [docs/PARITY.md](docs/PARITY.md) for the checked scope and explicit rule differences.

See [ARCHITECTURE.md](ARCHITECTURE.md), [EXPERIMENTS.md](EXPERIMENTS.md), [BENCHMARKS.md](BENCHMARKS.md), and [data/SOURCES.md](data/SOURCES.md).


Current engine: `splendorust-v2`. At the `u32` turn-counter limit the core returns
an atomic `TurnLimit` resource error, not a game outcome. Old v1 replay files
require the matching v1 source; current versioned fixtures and migration evidence
are documented in [VALIDATION.md](VALIDATION.md).

Search and Strong also apply the public next-turn bound to complete token
returns. They avoid a take that empties the colored bank and proves that the
next actor cannot act, when another choice exists. A blind opponent reservation
prevents this proof. The check does not reject a take that finishes an already
active final round, or that ends the game through an already eligible noble
from the last seat. E20 and E21 record the failed candidate and fresh checks;
E22 records the noble boundary correction.
These policies do not guarantee termination for all setups or budgets.
