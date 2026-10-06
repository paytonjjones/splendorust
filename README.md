# Beat the Bot! 

[Play in the browser](https://splendorust.pages.dev). 

I do not know if the bot is superhuman. Let me know if you beat it!

# SplendoRust

SplendoRust is a very, very fast engine for playing and simulating Splendor. 

Please feel free to use it to train your own bot, simulate games, etc. 

It aims to exactly match the rules of base Splendor for 2-4 players. It can also use flags to alter certain rules, in case you need to match common modified-rules targets. 

As of 10/26, it runs faster than any comparable engine I could find:

| Workload (one worker, Apple M4 Pro) | seal256 C++ | AhinLendor C++ | **SplendoRust** |
| --- | ---: | ---: | ---: |
| [Aligned random play](benchmarks/results/current-20261006/REPORT.md#aligned-play) | 22.9k games/s | 37.0k games/s | **86.2k games/s (2.3×)** |
| [Aligned fixed play](benchmarks/results/current-20261006/REPORT.md#aligned-play) | 23.4k games/s | 35.0k games/s | **81.0k games/s (2.3×)** |
| [Replay](benchmarks/results/prepared-replay-20261006/REPORT.md#common-timing-contract) | — | 850k replays/s | **1.12MM replays/s (1.3×)** |

## Bot

The main purpose of this repository is the engine. 

As a proof of concept, the engine was also used to train a bot, currently implemented as an Entity Transformer. The bot receives only the human-available observation of the game, not the full game state. 

The bot won **77.5%** of 1,000 games against the best competitor open-weights bot I could find, an implementation of [AlphaZero](https://github.com/lyquentxy/splendor/tree/32a27ac1f85d5de2766cc5f60c2bf04e557f7836). After bolstering the AlphaZero search/compute to be more comparable, the SplendoRust bot still won [58.85%](research/sprint48/opponent_search/RESULT-6400.md) of games. Note that AlphaZero uses slightly different rules than base Splendor; I compared using AlphaZero's ruleset. 

## Run locally

To set up. 

```sh
cargo run --release --locked -- play --agents strong,greedy --seed 42 --check --output game.json
cargo run --release --locked -- replay game.json
```

## Download the bot weights

The current bot weights are public under the [MIT license](LICENSE).
[Download the Rust/WASM model](https://raw.githubusercontent.com/paytonjjones/splendorust/main/web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin)
or [the compressed PyTorch checkpoint](https://raw.githubusercontent.com/paytonjjones/splendorust/main/research/training_strategy/artifacts/core/chunks/first/onehot/runtime.pt/0000.gz).
[The weights guide](docs/CHAMPION.md) explains the formats, hashes, and setup.

The browser build selects the model from
[the strength champion record](research/STRENGTH_CHAMPION.json) and runs its weights locally in Rust/WASM. 

Some legal games can stop with no legal action or can repeat token moves.
These games have no winner. Read [the rule and validation guide](VALIDATION.md)
before you use comparison results.

## Artifacts

| Document | Use it to |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | Understand the crates, decisions, hidden information, and replay. |
| [Validation](VALIDATION.md) | Check rule choices, test coverage, and evidence limits. |
| [Benchmarks](BENCHMARKS.md) | Measure speed and find performance results. |
| [Experiments](EXPERIMENTS.md) | Find research results and earlier trials. |
| [Strategy](STRATEGY.md) | Plan a new experiment. |
| [Data sources](data/SOURCES.md) | Check the source of the 90 cards and 10 nobles. |
