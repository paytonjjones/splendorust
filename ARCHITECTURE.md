# Architecture

Current model/search work follows [STRATEGY.md](STRATEGY.md). Model size,
search depth, and equal compute are not final strength limits. Isolated
research tensor services may use ML frameworks; the core stays independent.
Historical baseline descriptions below do not constrain new agents.

## Crates

- `splendor-core`: static metadata, fixed-size state, explicit SplitMix64 RNG, setup, action generation, action validation, transitions, observations, hidden-state sampling, and invariants. Its only production dependency is `arrayvec`. No I/O, serialization framework, clock, global RNG, or agent code.
- `splendor-agents`: observation-only `Agent` trait, uniform random, two integer heuristics, and root UCB Monte Carlo search. The search clock is optional and outside the core.
- `splendor-arena`: CLI, Rayon scheduling, statistics, JSON event snapshots, replay, and result reports.

Unsafe Rust is forbidden in the three libraries. Full engine state fields are private. Cards use IDs 0–89; nobles use IDs 0–9. Colors are white, blue, green, red, black, then gold. `NONE = 255`. Purchased cards use a `u128` bitset; nobles use a `u16` bitset. The full state uses fixed storage. Cloning copies the state; there is no apply/undo path because measured clone cost is small.

## Decision phases

A complete player turn can require more than one agent decision:

1. `Main`: take gems, reserve a visible card, reserve from a deck, or select a card to buy.
2. `Payment`: choose the colored tokens to pay. Gold pays the remaining discounted cost, including voluntary substitution.
3. `Return`: choose the complete bundle of excess tokens to return.
4. `Noble`: choose one eligible noble, only when more than one qualifies.
5. Finish the turn and advance the seat. A single eligible noble is claimed automatically.

Payment and return are alternatives in ordinary turns. Pending decisions retain the current player. Only completed player turns increment `turns`. The engine checks the end-game trigger after the full turn. Seat zero starts; all players receive equal turns at the normal game end.

`ActionSet` has stack storage for 256 actions. The largest payment space has 252 possibilities: distribute at most five gold substitutions across five colors. At most three tokens must be returned, giving at most 56 bundles over six colors. A loose upper bound for main decisions is 45 choices. Noble choice has at most five. Enumeration order is stable and unchanged from engine version 1 in version 2.

This avoids a large Cartesian product of main moves, payments, returns, and noble choices. `RandomAgent` is uniform per decision phase. It is not uniform over all compound complete-turn paths. Consumers must distinguish decisions from player turns.

`apply_action` validates directly before mutation. It does not rely on the agent or on a caller-supplied action list. Rejected actions leave the state unchanged. No heap allocation occurs in setup, cloning, legal generation, apply, or observation. Search and arena bookkeeping may allocate. A release integration test directly counts allocation calls over 768 fixed-seed core trajectories and every legal branch at their sampled states. It reaches all phases and action types with zero allocations; a deliberate allocation confirms the counter works. This is sampled evidence, not a proof for every reachable state. The test-only allocator wrapper is outside the unsafe-free production library. See `docs/results/core-allocation-validation.json`.

## Hidden information

An `Observation` contains public tokens, bonuses, points, purchased cards, nobles, market cards, deck sizes, reservation counts/tiers, and the viewer's private reservations. It contains no setup seed, random state, future deck order, or opponents' blind-reserved card IDs. A visible reservation stays known because an agent can legally remember the revealed card.

Blind cards use `NONE` in opponent observations, so use `reserved_counts` rather than `Player::reserve_count()` on a redacted opponent. Slots stay compact. Reservation tier is observable because the deck chosen was observable.

`Observation::determinize` assigns all unknown cards without replacement within each tier, then shuffles future decks. It verifies the reconstructed state. Root search receives only the observation and legal list. Each rollout player gets its own redacted observation. No API passes the real engine to an agent.

The sampler models unknown cards uniformly. It does not condition on inferred opponent preferences or bidding history. Root UCB search restricts candidates to the top `width` heuristic actions and estimates their value through fixed-depth policy rollouts. Each simulation samples a fresh world. It has no persistent tree, shared-world belief updates, or claim of game-theoretic optimality. This is an initial determinization baseline.

When search has three reservations and only token takes are legal, it first
checks a sufficient bound for a legal next turn. A take without excess tokens
passes if the colored bank cannot be emptied in the remaining opponent turns,
an own reserved card becomes affordable, or opponents lack enough turns both
to empty the bank and remove every affordable market card. Each opponent can
take at most three colored tokens or remove one market card per turn. Search
restricts its root choices only when both passing and failing takes exist.
This check uses public bank/market data and the actor's own cards. It also
applies to zero-iteration search. It does not change rollout policy, guarantee
full-game completion, or assign an outcome to a blocked game.

## Determinism and replay

SplitMix64 uses explicit wrapping `u64` operations and rejection sampling for bounded values. Fisher–Yates shuffles each tier, then nobles, in a fixed order. Seed and action sequence determine every subsequent state; drawing cards does not call a hidden RNG.

Arena setup `b` uses `SplitMix64(base_seed + b).next_u64()`. Arithmetic wraps explicitly. Each agent identity gets a separate seed derived from setup seed and identity. Seat rotation changes seating without changing those identity seeds. Rayon results are collected in game-index order, and statistics are reduced in that order.

The integer core and heuristics are portable. Root UCB uses floating-point `ln` and square root; fixed iteration runs are deterministic on the tested target/toolchain. A 1,700-game fixed-budget comparison agrees between native ARM macOS, x86_64 macOS under Rosetta, and ARM Linux with Rust 1.98.1 (see VALIDATION.md). General cross-platform equality for search choices is not claimed. Recorded actions replay independently of search math.

A version-1 JSON `History` is an event-sourced state snapshot: engine version, player count, setup seed, action tags and payloads, and a diagnostic full-state string. Loading reconstructs setup and applies every decision with invariant checks, then checks the diagnostic snapshot. Any prefix is also a valid snapshot, including payment, return, and noble phases. This format favors auditability over constant-time loading. It contains privileged data and must not be passed to an agent.

Action tags: 0 take, 1 visible reserve, 2 blind reserve, 3 visible buy, 4 reserved buy, 5 payment, 6 return, 7 noble. Each record is seven bytes in JSON integer-array form; unused payload bytes must be zero. Incompatible engine versions are rejected rather than silently reinterpreted.

## Outcomes and statistics

Normal rank uses prestige descending, then purchased-card count ascending. Exact ties share a competition rank and split one win credit. Reserved cards do not break ties. An unfinished state has no outcome.

The official rules neither force eventual progress nor explain a turn with no legal main action. Core does not add a pass or a move-limit victory. The arena stops such games as `no_legal_action`, and stops looping policies as `decision_limit`. Both remain in per-game records. Decision-limit games reject promotion. No-action outcomes remain unknown; the current conservative policy allows at most 1%, as specified in VALIDATION.md.

Confidence intervals cluster the seat rotations from one setup. They use the bounded empirical Bernstein interval of Maurer and Pontil (2009), Theorem 4, applying alpha/2 to each tail: `log(4 / 0.05)`. Missing outcomes contribute worst-case credit 0 to the lower bound and 1 to the upper bound. This avoids selective deletion of failed games. Intervals assume independent random setups and a policy fixed before evaluation. These are conservative intervals, not normal/Wald intervals. No Elo is reported for multiplayer games.

Source: https://arxiv.org/abs/0907.3740


Engine version 2 adds a checked turn-counter resource limit. `apply_action`
validates rule legality first, then returns `TurnLimit` without mutation when
`turns == u32::MAX`. This leaves legal enumeration intact and assigns no outcome.
Search stops rollouts at capacity; arena execution errors propagate to callers.
Replay version 1 remains the JSON format, while the engine label must match v2.
See VALIDATION.md for fixture migration and boundary evidence.

The public next-turn bound also applies to Strong and to complete return
bundles. Search and Strong separately reject a take that would empty the
colored bank into a proven block for the next actor, if another choice exists.
That proof requires three known reservations and no affordable market or
reserved card. Unknown blind reservations, pending token returns, and a take
that completes an active final round prevent that proof. A last-seat take also
escapes the guard when an already eligible noble raises prestige to at least
15, even if the final-round flag was false before the take. The check uses only
Observation. It changes real policy choices. Search rollouts still use the existing
uncertified heuristic scoring; core rules do not change.
