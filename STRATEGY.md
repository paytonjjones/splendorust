# Research strategy

The goal is stronger play from valid observations. Keep the evidence clear
enough to show what improved and under which conditions.

## Current position

The 48-hour campaign is complete. Its confirmed agent beat pinned unchanged
AlphaZero800 with 77.5% win credit in 1,000 complete native-profile games. The
conservative 95% lower bound was 71.43%, above the registered 55% target.
See [the result](research/sprint48/RESULTS.md).

The separate AlphaZero6400 diagnostic also finished. It earned 58.85% credit
at equal simulation counts. Its conservative lower bound was 52.78%, so it
did not pass the decisive target. Equal simulation counts do not mean equal
compute. See [the diagnostic](research/sprint48/opponent_search/RESULT-6400.md).

The AhinLendor follow-up has a public-observation adapter and engine-speed
evidence. Its flagship strength test lacks trained weights. See
[the source audit](research/ahinlendor/SOURCE_AUDIT.md) and
[the engine result](research/engine-throughput/RESULTS.md).

The completed campaign's schedule is
[kept in the strategy history](docs/history/STRATEGY.md).
Do not restart its completed trials, final seeds, or deadline.

## Select the baseline

| Record | Purpose |
| --- | --- |
| [STRENGTH_CHAMPION.json](research/STRENGTH_CHAMPION.json) | Confirmed research agent, model hashes, search profile, and result. Use this as the research baseline. |
| [CHAMPION.json](research/CHAMPION.json) | Older E81 standalone model and canonical result. It remains available as a control. |
| [EFFICIENCY_CHAMPION.json](research/EFFICIENCY_CHAMPION.json) | E81's measured cost comparison against the tested models. This is a limited efficiency result. |

The browser build now selects `STRENGTH_CHAMPION.json`. It can run the exported
Entity weights locally in Rust/WASM. The confirmed native campaign used a
checkpoint-bound tensor service; that service is not required by the browser.
See [the weights guide](docs/CHAMPION.md) and
[web setup](docs/WEB_DEPLOYMENT.md).

Do not use an older latency or model-size limit to reject a stronger candidate.
More parameters, search depth, simulations, or unequal compute are allowed.
Measure cost so that the selected final test can finish.

## Plan one bounded experiment

1. Read the relevant [experiment results](EXPERIMENTS.md). Reuse saved data,
   models, and checks where they answer the same question.
2. Write one hypothesis before an agent change. State the changed behavior,
   control, finite resource budget, and decision rule.
3. Use small fixed exploratory screens to select a branch. Keep failed and
   uncertain results. Do not select an agent only from prediction loss.
4. Measure complete-game cost. Reserve enough time for final play, replay,
   analysis, and delivery. One owner schedules heavy CPU and GPU jobs.
5. Freeze one final model, backend, search profile, opponent, rules, fresh seed
   set, and sample size before outcomes. Earlier used setups are not fresh.
6. Finish the fixed sample. Do not stop when an interval first looks favorable,
   add games after an unfavorable result, or select another model from final
   outcomes.
7. Save the evidence and state the supported conclusion. Change a champion
   record only when confirmed evidence supports it.

A 2,000-game development screen or a 20,000-game confirmation is not a universal
requirement. Choose counts before outcomes to fit the question and budget.

## Protect the result

- Agents receive `Observation` only. Never provide the setup seed, real deck
  order, or an opponent's blind reservation.
- Keep every legal payment, token return, and mandatory noble choice.
- Keep the core independent of agents, I/O, clocks, serialization, and ML
  frameworks. Normal core transitions must not allocate. Isolated research
  code can use PyTorch, MPS, or another local backend. Game decisions must not
  call an LLM service.
- Record the exact opponent and rules profile. A canonical result does not
  predict a native-profile result.
- Keep all requested games and seat rotations. Unknown games have no winner.
  Use conservative bounds and the [completion policy](VALIDATION.md#games-that-do-not-finish).
- Freeze exact binaries and model files. A different numerical backend can
  change decisions and must be tested as a declared candidate.
- Preserve failed runs, old decisions, raw records, and source/model identity.
  Never train on a final test.

For the pinned AlphaZero target, use the native harness and its statistics
computed from game records. Keep the opponent source, checkpoint, and declared
search settings fixed within each test. Report native score caps and a second
bound that treats those caps as unknown. For canonical promotion, use
`scripts/promote.py` and its completion and interval checks.

## Deliver a reproducible result

Save the model, lineage, data and training recipe, source and binary hashes,
search and backend settings, raw games, replay checks, statistics, costs, and
failed trials. Provide a working restore or run command. State the limits of
the claim, including rules, information, and compute differences.

Run required checks locally after Rust changes. GitHub Actions stays disabled.
See [Validation](VALIDATION.md#run-local-checks). The browser interface is outside
the strength campaign's research scope.
