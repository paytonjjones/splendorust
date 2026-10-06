# Sprint 48 next search options

The current evidence is exploratory. Parent reports Trial 02 at 47.27% credit
for PUCT1600 with fresh worlds, Trial 03 at 38.28% for Gumbel1600, and Trial
00 at 45.70% for one-hot Gumbel128. Trial 04 is testing PUCT1600 with three
chance universes. These are separate 128-game screens with broad uncertainty.
They do not identify a reliable winner between profiles.

## Ranked options

### 1. Test dynamic FPU on the frozen PUCT candidate

This is the strongest next search change to test after Trial 04 completes.
It matches a concrete difference from pinned AlphaZero and has low cost. Keep
the checkpoint, PUCT iterations, depth, world pool, chance universes, worker
count, batch, and delay fixed. Change only `dynamic_fpu=false` to `true` on a
fresh exploratory master. A 128-game screen should cost about the same as the
current screen, roughly 20-25 minutes at the reported service rate.

Pinned AlphaZero stores the network leaf value in `Qs` when it first expands a
node (`local/strength/external/alphazero/MCTS.py:153`). After each backup it
updates `Qs = ((Ns + 1) * Qs + v[0]) / (Ns + 2)` (`:179`) and uses `Qs - fpu`
for an unvisited action (`:214`). This is a one-count prior from the initial
network value plus all backed-up values. Native PUCT currently uses the fixed
leaf value `node.value - fpu_reduction` (`crates/splendor-agents/src/neural_search.rs:660-664`)
unless `dynamic_fpu` is enabled. Its update at lines 687-691 uses the same
pseudocount average in probability space. The configured `.02965` is half the
pinned signed-space `.0593`, so the scale matches for two-player values.

The native value perspective appears consistent. Upstream backs up canonical
player-0 values and rotates them at player transitions (`MCTS.py:175-179`).
Native stores absolute player credits, returns `[p, 1-p]` at leaf evaluation,
and accumulates `values[seat]` for the actor's edge
(`neural_search.rs:626-634, 664-691`). The Entity training loss uses opposite
signed outputs for the two seats (`research/sprint48/branch2_train.py:104-107`).
The native worker also requires `viewer == current` before search
(`crates/splendor-arena/examples/native_policy_worker.rs:142-145`). I found no
perspective reversal in this path.

An optional `dynamic_fpu` boolean now exists in the native worker reset
request. It defaults to false, rejects non-booleans, sets the existing agent
field, and appears in the accepted-settings receipt. Existing requests keep
their behavior. This interface change has a focused parser test. The live
Trial 04 worker was frozen before this source change and is unchanged.

### 2. Run the ready learner-state DAgger branch

This has the larger possible model gain, but more cost and weaker evidence.
It trains on candidate states with fixed AlphaZero800 action, selected-edge
Q, and terminal-credit targets. Current source labels cover only 64 setup
blocks. The revised train/dev schedules target 512/128 disjoint paired setups. Use
the prospectively declared 10% DAgger loss and its 90% full-dev / 10% DAgger-dev
selector; evaluate on fresh paired games. See DAGGER_BRANCH2_PREREGISTRATION.md
for the current fixed recipe. Do not add visits or a new Q head in the same branch.
The evidence for richer targets is weak: the prior direct visits/one-hot and
Q/visits screens did not support a target change (`research/training_strategy/RESULTS.md`).

### 3. Consider public-observation subtree reuse after the first two tests

Pinned AlphaZero keeps one MCTS tree for each game and reuses full-board-keyed
descendants between turns (`benchmarks/strength/native/upstream.py:77-89`,
`MCTS.py:39-45, 86-91`; `SplendorGame.py:59`). Native PUCT creates new nodes
and an index at every decision (`crates/splendor-agents/src/neural_search.rs:770-785`).
Reuse may save work after a no-refill action. It is lower priority because
native sees only the acting player's public observation. The observation masks
an opponent's blind-reserved card (`native_environment.rs:286-299`), while
cached visit/value aggregates can preserve a stale hidden-world posterior
after a reveal. A future test must store no determinized state or deck bits,
key only by public observation/history, require an exact descendant-root hit,
and compare against a fresh tree at the same new-simulation budget. Record
root hits and retained visits. Keep Gumbel fresh-root search out of this test.

### 4. Measure the depth cap before changing it

Pinned AlphaZero has no fixed search-depth cap; it expands until a terminal
state or a new leaf (`MCTS.py:120-153`). Native PUCT stops at configured depth
in `neural_search.rs:601-604`. Depth 32 could affect a narrow endgame branch,
but high branching may keep most 1,600-simulation traversals below it. There
is no current count of simulations that reach the cap, so increasing depth
now would be speculative. If more search work is planned, first record the
fraction of traversals stopped by depth versus an unexpanded leaf.

The UCB scale also differs slightly: pinned code uses `sqrt(Ns)` for visited
and `sqrt(Ns + EPS)` for unvisited edges (`MCTS.py:214-225`), while native
uses `sqrt(node.visits + 1)` for both (`neural_search.rs:664-669`). This makes
native exploration larger by `sqrt((N+1)/N)` at a node with N visits, which is
largest early and quickly approaches one. It is a smaller first test than
dynamic FPU and should not be changed in the same comparison.
