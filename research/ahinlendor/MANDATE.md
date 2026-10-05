# Next goal: close AlphaZero6400, then benchmark against AhinLendor

We have already achieved the main AlphaZero result:

- SplendoRust Entity + PUCT6400 decisively beat the unchanged pinned AlphaZero800 configuration.
- Final result: 77.5% win credit over 1,000 games, conservative paired 95% interval 71.43–83.57%.
- This is sufficient evidence that we beat the published/pinned AlphaZero configuration on its native benchmark.
- A separate AlphaZero6400-vs-SplendoRust6400 run is currently underway. This is a stronger diagnostic, but it is **not a prerequisite** for the established AlphaZero800 claim.

The broader goal is now:

> **Establish the strongest publicly documented two-player Splendor bot, and understand whether SplendoRust's simulator is also state of the art in raw engine performance.**

The strongest relevant public contender we have identified is:

**AhinLendor**  
https://github.com/inhabae/AhinLendor

It is an AlphaZero-style Splendor agent with a native C++ engine. Its repository claims:
- Rank 1 on the Spendee ladder.
- The underlying game is effectively base Splendor: its Spendee bridge maps all 90 standard development cards and all 10 standard nobles one-for-one to its Splendor engine.
- Earlier Rank-1 play used roughly 70,000 MCTS simulations under a 5-minute + 10-second/action control.
- Its later stronger configuration uses roughly:
  - 250,000 MCTS simulations
  - 20,000 bootstrap iterations per legal root action
  - batched leaf evaluation
  - around **20 seconds per move on a MacBook M2**
- The README discusses games against very strong / former #1 Board Game Arena players.

There are some small engine-rule differences/edge cases, so **do not use AhinLendor's engine as the referee for the bot-strength comparison**.

---

# Phase 1 — close the AlphaZero6400 run cleanly

First, deal with the currently running fixed AlphaZero6400 follow-up.

Do **not** restart it or alter its seeds.

Use the existing recovery/completion machinery and extract the strongest valid evidence available from the preregistered sample.

If all 1,000 planned games complete and validate, report the complete result.

If the run cannot validly finish before we move on:
- preserve every completed shard and receipt,
- report exactly how many preregistered paired games completed,
- calculate the corresponding clearly labeled exploratory estimate/interval if statistically legitimate,
- explain why the fixed confirmatory claim could not be completed,
- do not substitute new seeds or silently shrink the preregistered sample.

Archive/document this work and consider the AlphaZero line closed afterward unless the result reveals something genuinely surprising.

Do not spend substantial additional research time optimizing against AlphaZero.

---

# Phase 2 — integrate AhinLendor as an external opponent

The priority is a **small but credible head-to-head strength benchmark** against AhinLendor.

## Neutral referee

Use SplendoRust's canonical two-player base-Splendor engine as the referee, after auditing it against the official base-game rules.

AhinLendor should receive only the information legally observable to a player:
- public board/state
- its own reserved-card identities
- public history/inferences that naturally follow from gameplay
- no true hidden opponent reservation identity
- no future deck order

SplendoRust gets the same information boundary.

Do not allow either implementation's internal game engine to leak hidden state into its search.

Build an adapter from canonical SplendoRust observations/legal actions to AhinLendor and back.

Audit the mapping carefully:
- all 90 cards
- all 10 nobles
- visible/reserved/blind reservations
- token taking and returns
- gold
- noble choice
- end-of-round / game-ending logic
- tie breaking
- legal-action mapping

Where SplendoRust and AhinLendor engine semantics differ, the **neutral SplendoRust referee is authoritative** for this benchmark.

Preserve those discrepancies in the report.

---

# Phase 3 — benchmark on AhinLendor's documented flagship terms

The primary comparison should answer:

> At approximately the per-move compute regime AhinLendor publicly uses for its strongest documented human-facing agent, which bot is stronger?

Use **20 seconds of wall-clock thinking time per decision per agent** as the primary budget.

This is preferable to forcing equal simulation counts because one simulation in the two engines/search implementations is not equivalent.

Both agents may use:
- their preferred search implementation,
- batching,
- CPU/GPU acceleration,
- their own neural network,
- their own documented search enhancements,

provided:
- they stay inside the same 20-second decision budget,
- they receive the same legal game information,
- the neutral referee determines legality and outcomes.

For AhinLendor, first reproduce as closely as practical its documented strongest public configuration:
- MCTS
- bootstrap search if used by its current flagship configuration
- batching
- its released checkpoint
- its intended hidden-information handling

Do not intentionally handicap it merely to make integration easier.

For SplendoRust, use our **strongest practical agent**, not an old fixed-Gumbel128 research configuration. Start from the current strength champion and tune only enough to use the 20-second budget effectively.

### Keep this benchmark initially small

Do not immediately run another 1,000-game campaign.

First:
1. verify exact rule/action parity,
2. run tiny smoke matches,
3. measure actual decision times,
4. then run a modest fresh paired comparison sufficient to tell whether the gap looks large or small.

Something like 100–250 games is reasonable for the first real screen, depending on cost.

If one agent is winning overwhelmingly, stop after enough evidence to establish that and report it.

If it is close, preserve the result and propose a larger confirmation separately.

Swap seats on matched setups.

Record:
- W/L/D
- paired win credit
- uncertainty interval
- average and percentile decision time
- simulations/search nodes where available
- neural inference count
- failures/timeouts
- search settings
- exact checkpoint/source hashes

Do not claim "world's strongest" from a tiny noisy win.

---

# Phase 4 — directly benchmark the two game engines

A second important claim of SplendoRust is that its simulator is extremely fast.

AhinLendor has a native **C++17** engine, so benchmark it seriously. If its simulator is faster, we need to know.

This is independent of neural inference and MCTS strength.

## Benchmark objective

Compare the **raw canonical game-state engines** under as nearly identical work as possible:

**SplendoRust Rust engine vs AhinLendor C++ engine**

Measure at least:

### Primitive operations

- clone/copy game state
- enumerate legal actions
- apply a supplied legal action
- clone + apply
- terminal/winner check
- observation/public-state construction if comparable
- random legal trajectory / complete random game

### Search-relevant throughput

Also create one or more representative workloads such as:

- starting-state repeated clone → legal-actions → apply
- random midgame positions
- late-game positions
- full random playouts
- tree-like repeated expansion from a fixed corpus of states

Use the **same predetermined positions/actions** where possible, not independently generated workloads that may differ in complexity.

## Benchmark fairness

Compile both in optimized release mode appropriate to their languages.

For example:
- Rust release build with the project's normal performance