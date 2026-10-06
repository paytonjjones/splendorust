# Experiments

This guide points to the main research results. Each result applies to its
recorded opponent, rules, information, and compute budget. Do not combine
results from different profiles into a general ranking.

Canonical tests use this engine's base-game rules. Native tests use an external
opponent's rules profile. Those rules can differ.

## Confirmed strength result

The first one-hot Entity model with PUCT6400 earned **77.5% win credit**
against pinned unchanged AlphaZero800 in **1,000 complete games**. The
conservative paired 95% interval was **71.43–83.57%**. Its lower bound passed
the registered 55% target. All games ended by native score, with no unknown
outcomes or caps. Replay and the final audit passed.

The candidate used 6,400 simulations per decision, depth 64, three sampled
worlds, and three chance universes. AlphaZero kept its model and 800 simulations.
The test used AlphaZero's native rules and private-information interface;
Splendorust used observations and its own private cards. This establishes a
win in that profile with unequal compute. It does not establish a world rank,
a canonical-rule rank, or strength against expert humans.

See [the result](research/sprint48/RESULTS.md),
[the final decision](research/sprint48/FINAL_DECISION.json), and
[the champion record](research/STRENGTH_CHAMPION.json).
[The weights guide](docs/CHAMPION.md) has public downloads and file hashes.

## Main results and lessons

| Study | Result | Use it to |
| --- | --- | --- |
| [AlphaZero6400 diagnostic](research/sprint48/opponent_search/RESULT-6400.md) | 58.85% credit in 1,000 complete games; conservative 95% interval 52.78–64.92%. | Check the result at equal simulation counts. The decisive 55% lower-bound target was not met; total compute still differs. |
| [Architecture study](research/architecture_pivots/REPORT.md) | Expanded Entity earned 60.7225% against E81 in 20,000 complete canonical games at Gumbel128; 95% interval 59.595–61.850%. | Reuse the confirmed representation gain. Residual capacity and the tested history recipe did not show the same benefit. |
| [Training study](research/training_strategy/RESULTS.md) | The first one-hot update improved its canonical screen. Later target and iterative controls did not establish further gains. | Reuse saved models and failed trials before collecting more data. |
| [E83 milestone](research/e83/REPORT.md) | E81 earned 54.8625% against E56 in 20,000 complete canonical games. | Understand the older standalone model and search record. |
| [E95 supervision](research/e95/HANDOFF.md) | 6,000 expert games and their datasets were saved and checked. | Find the data reused by later architecture work. The handoff describes its own earlier stopping point. |
| [AhinLendor audit](research/ahinlendor/SOURCE_AUDIT.md) | No trained checkpoint or documented download was available. | Understand why adapter and engine-speed checks do not establish flagship playing strength. |

A small exploratory result can help select the next trial. It does not replace
a fresh final test. A lower prediction loss does not prove stronger play.
Failed and uncertain results remain part of the record.

## Earlier experiments

[The experiment history](docs/history/EXPERIMENTS.md) contains E1–E95,
the completion-policy changes, hypotheses, failed candidates, seeds, decisions,
and evidence paths. It preserves the earlier stage descriptions and rules.
Use [Strategy](STRATEGY.md) for new work.

The history includes heuristic baselines, cycle and block checks, search
budgets, inference changes, teacher labels, and model training. Detailed game
reports are indexed in [the evidence index](docs/results/index.json).
Small-model ancestry is in [the lineage record](research/LINEAGE.json).

## Record a new experiment

Before an agent change, write a hypothesis and a finite resource budget.
Keep training, model-selection, and final-test setups separate. Freeze the
candidate and final sample size before final outcomes.

Save the command, source and binary hashes, model and data hashes, search
settings, seeds, all game records, replay checks, intervals, and measured cost.
Record failed runs and uncertain results. Use `scripts/promote.py` for a
canonical promotion decision. Keep its decision separate from external-profile
results.

See [Validation](VALIDATION.md) for unknown outcomes and
[Benchmarks](BENCHMARKS.md) for timing requirements.
