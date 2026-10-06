# Splendorust

Splendorust is a Rust engine for base Splendor with 2–4 players. Use it to
run games, compare agents, and check saved games. It also has a browser game.

## Play

[Play in the browser](https://splendorust.pages.dev). You play a two-player
game against a model that runs on your device. The game footer identifies the
loaded model. Use a mouse, touch, or the arrow keys and Enter. Visitor games
are recorded for research.

For local setup and deployment, see [the web guide](docs/WEB_DEPLOYMENT.md).
For recorded games, see [the game log guide](docs/web/GAME_LOGS.md).

## Run locally

Install Rust with rustup. The repository selects Rust 1.98.1 and uses the
locked dependencies in `Cargo.lock`. Run these commands from the repository root:

```sh
cargo run --release --locked -- play --agents strong,greedy --seed 42 --check --output game.json
cargo run --release --locked -- replay game.json
```

The first command runs one game and saves its actions. `--check` checks the
state after each decision. The second command checks the saved game.

To compare two agents:

```sh
cargo run --release --locked -- compare --agent-a search --agent-b strong --games 1000 --seed 100001 --threads 4 --iterations 128 --depth 8 --output comparison.json
cargo run --release --locked -- verify-report comparison.json
```

Each setup is played with every seat rotation. The game count must be a
multiple of the player count. `verify-report` runs the saved settings again
and compares every game record. It requires the same source and engine version.
This example is a small comparison, not a formal strength claim.

Run `cargo run --release --locked -- --help` for all commands. Add `--help`
after a command name for its options.

## Choose an agent

| CLI name | Behavior |
| --- | --- |
| `random` | Selects a random legal action at each decision. |
| `greedy` | Buys affordable cards and favors points and useful bonuses. |
| `strong` | Favors efficient purchases, useful tokens, and noble progress. |
| `search` | Samples unknown cards and tests actions with simulated play. |

These agents work without a model service. Neural research agents also need
model files. Some research backends use a separate inference service. See
[the research guide](STRATEGY.md) before you use them.

## Download the champion weights

The champion weights are public under the [MIT license](LICENSE).
[Download the Rust/WASM model](https://raw.githubusercontent.com/paytonjjones/splendorust/main/web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin)
or [the compressed PyTorch checkpoint](https://raw.githubusercontent.com/paytonjjones/splendorust/main/research/training_strategy/artifacts/core/chunks/first/onehot/runtime.pt/0000.gz).
[The weights guide](docs/CHAMPION.md) explains the formats, hashes, and setup.

## Understand the results

The confirmed research agent earned **77.5% win credit** in 1,000 complete
games against the pinned AlphaZero800 agent. A win gives one credit; an exact
tie splits that credit. The conservative 95% interval was **71.43–83.57%**.

The research agent used 6,400 search simulations per decision; AlphaZero used
800. The test used AlphaZero's own rules profile, which differs from this
engine's base-game rules. It does not establish strength at equal compute,
under all Splendor rules, or against expert humans. See
[the full result](research/sprint48/RESULTS.md).

The browser build selects the model from
[the strength champion record](research/STRENGTH_CHAMPION.json) and runs its
exported weights locally in Rust/WASM. The native research test used a separate
inference service. [CHAMPION.json](research/CHAMPION.json) retains the older E81
model and canonical result.

Some legal games can stop with no legal action or can repeat token moves.
These games have no winner. Read [the rule and validation guide](VALIDATION.md)
before you use comparison results.

## Find more information

| Document | Use it to |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Understand the crates, decisions, hidden information, and replay. |
| [Validation](VALIDATION.md) | Check rule choices, test coverage, and evidence limits. |
| [Benchmarks](BENCHMARKS.md) | Measure speed and find performance results. |
| [Experiments](EXPERIMENTS.md) | Find research results and earlier trials. |
| [Strategy](STRATEGY.md) | Plan a new strength experiment. |
| [Data sources](data/SOURCES.md) | Check the source of the 90 cards and 10 nobles. |

GitHub Actions is disabled. Run checks locally as described in
[Validation](VALIDATION.md#run-local-checks).
