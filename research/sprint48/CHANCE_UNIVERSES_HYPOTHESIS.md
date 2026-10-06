# Sprint 48 chance universes and subtree reuse

This note records source evidence for two search differences. They are
hypotheses for later tests. They do not explain a measured strength result.

## Chance draws

Pinned AlphaZero revision `32a27ac1f85d5de2766cc5f60c2bf04e557f7836` uses
three deterministic chance seeds per root search. In
`local/strength/external/alphazero/MCTS.py`, line 25 defines
`magic_seeds = [31416, 1, 14142, 42, 27183, 2, 16180, 7]`; line 63 selects
`magic_seeds[self.step % self.args.universes]` once per simulation; lines
164-172 pass the same `self.random_seed` to the selected transition. The
recursive search call at line 175 keeps that seed for later transitions in
the same simulation. `MCTS.py` lines 234-240 pass it to
`gameboard.make_move`.

In `local/strength/external/alphazero/splendor/SplendorLogicNumba.py`, lines
306-326 use ordinary random sampling when the seed is zero. A nonzero seed
selects a card by applying the seed to a hash of the remaining tier cards.
Thus, for a fixed hidden deck state, the three-universe profile uses at most
three deterministic outcomes for a given refill state and action. It does not
retain three deck orders, and different hidden determinizations can still add
more aggregate public children.

Native search had no such seed before the optional chance-seed path was added.
`crates/splendor-agents/src/environment.rs` lines 22-29 define a default
`apply_with_chance_seed` that calls the original `apply`; the native override
is at lines 134-141. `native_environment.rs` lines 345-365 use `rng.index` for
an absent seed. Its buy, market-reserve, and blind-reserve refills pass that
seed at lines 412-425. Native tier sizes are 40, 30, and 20 cards before draws,
so “three versus 60” is only a loose intuition: one tier-1 refill has at most
40 possible cards, and fewer remain later.

`NeuralAgent::make_chance_seeds` in
`crates/splendor-agents/src/neural_search.rs` lines 334-343 creates a seed set
only when `chance_universes` is nonzero; `chance_seed_for` cycles it across
root simulations. `select_environment` passes that seed into each simulation
at lines 797-810. The seed comes from the agent's search RNG, not from a full
native state or deck. The seed is used only on search-side determinized states;
the actual game still applies its registered random transition. Canonical
`Environment` keeps its original transition through the default method.

The current 1,600-iteration PUCT result is close to the 128-iteration Gumbel
result in the parent report. This comparison changes more than one search
setting and has a small game sample. It does not show that chance handling
caused the small gap. The chance-universe mismatch is a concrete reason to
test an optional, pinned-style three-seed native PUCT profile on fresh
exploratory games. Keep `world_pool` as a separate setting: it samples hidden
states and does not set the refill seed.

## Tree reuse

The native benchmark calls `upstream.reset_policy(alpha_seed)` once for each
game in `benchmarks/strength/native/run.py` lines 88-90.
`benchmarks/strength/native/upstream.py` lines 77-82 creates one upstream
`MCTS` there. Its `nodes_data` map is initialized in `MCTS.py` lines 39-45 and
is retained between `choose` calls. The map is age-cleaned only after the
round advances by more than 20, removing nodes older than five rounds
(`MCTS.py` lines 86-91). The key is `board.tobytes()` through
`SplendorGame.py` line 59. The board stores remaining deck-card membership in
its rows 25-30, as described in `SplendorLogicNumba.py` lines 24-33. This is
a full-state key; it does not merge hidden deck partitions.

Native `select_environment` creates a new root `nodes` vector and `index` map
for each decision (`crates/splendor-agents/src/neural_search.rs` lines
770-785). It therefore loses descendant visits across actual moves. The
canonical `select_action` path has a separate optional persistent cache at
lines 910-918 and saves it at lines 1024-1026, but the native path does not use
that cache. Reuse may save work when an actual state matches a previously
searched descendant, especially after a no-refill action. It may not match
after a refill because actual chance sampling can differ from simulated
outcomes. No cache-hit rate or strength effect has been measured.

If chance universes give little benefit, a later native PUCT experiment can
test optional subtree reuse. It must key nodes by the acting player's exact
public `Observation` and relevant public-history hash, and retain only
aggregated nodes, never a determinized `State`, deck bits, or a hidden-card
identity. `native_environment.rs` lines 286-299 builds observations and masks
an opponent's blind reservation card with `NONE`. The cache must preserve
that boundary. It should reuse a root only when the next public key matches a
searched descendant, apply current legal-action restrictions, and clear on a
new game, missing root, or size limit. Gumbel search needs a fresh root budget
and should remain out of this test.

There is a material stale-belief risk. Native nodes merge simulations from
hidden worlds sampled at an earlier root. A later public reveal changes the
posterior over remaining cards. An exact public key prevents reuse across
different visible states, but it does not prove that old hidden-world value
averages match the new posterior. Compare reuse with a fresh-tree control at
the same new-simulation budget, record root hits and retained visits, and
include fresh held-out paired games before any adoption. Never use the true
referee state to select, key, or repair a search-cache entry.
