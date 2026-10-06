# Observation-only adapter

This adapter maps AhinLendor's pinned 69-action policy to semantic canonical
actions. The caller must build `BoardView` from the current acting player's
SplendoRust `Observation` and legal action list. It must never copy a
`GameState`, future deck order, or an opponent's blind reserved card identity.

`hydration.py` accepts only the versioned
`ahin-referee-observation-v1` JSON record. It maps the two-player public state
to Ahin's payload and samples identities for opponent blind reservations and
the tier draw piles from the unseen card pool. The caller supplies an
agent-owned sampling seed; the helper does not accept referee RNG or deck
state. It rejects payment/terminal prompts because the wrapper must complete
payment before asking Ahin for a new action. SplendoRust remains authoritative
for the final-round rule.

For the JSON-lines referee, `turn_id` stays constant during all canonical
substeps of one player turn; `decision_id` counts each referee prompt.
`pending_card_id` identifies the public card during a canonical payment phase.
Use `turn_id` plus `viewer` to enforce the single cumulative 20-second clock.

Rust market slots and Ahin market actions are both tier-major: four cards for
each of tiers 1, 2, and 3. Rust card IDs are zero-based; Ahin IDs are one-based.
All 90 card signatures match in the same order. Noble IDs do not: the exact
Rust-ID to Ahin-ID mapping is `(9, 8, 10, 6, 7, 5, 4, 2, 3, 1)`. The adapter
uses the canonical visible noble order to map Ahin's three noble slots back to
Rust IDs.

Ahin buys choose their payment automatically (colored tokens first, then gold).
The wrapper must apply that payment after the canonical `buy_*` intent. Ahin
returns are sequential and its action space cannot return gold. The wrapper
must collect all selected colors within the same 20-second turn budget, then
submit one canonical `return` vector. If the required return count exceeds the
held colored tokens, the position is incompatible with Ahin and must be recorded
as an adapter failure; the wrapper must not invent a different move.
The caller must keep one cumulative deadline across buy/payment, all token
returns, and noble choice. Ahin's `PASS_TURN` has no Rust action and is an
explicit compatibility gap.

Run focused mapping checks with the pinned interpreter used for the native
extension:

```sh
local/strength/inference/bin/python -m unittest discover -s research/ahinlendor/adapter -v
```

Build the local CPU extension first if it is not present:

```sh
local/strength/inference/bin/python research/ahinlendor/external/build.py
```

The Rust JSON-lines referee and scripted CPU smoke use:

```sh
CARGO_TARGET_DIR=local/research/ahinlendor/target-adapter cargo build --release --locked -p splendor-arena --example ahin_referee
local/strength/inference/bin/python research/ahinlendor/adapter/smoke.py
```

The smoke uses legal scripted actions. It loads no weights and measures no
playing strength. Its 20-second turn guard checks elapsed time after each
blocking operation. It does not preempt a blocked referee read or action
selection, so a future strength worker must enforce its own hard deadline.
The receipt records the phases and action types that the run actually reached;
tests cover mappings that a scripted game may not reach, such as noble choice.
The retained seed-1002 smoke receipt reached main, payment, return, and noble
phases: [smoke-full-phases.json](artifacts/smoke-full-phases.json).
