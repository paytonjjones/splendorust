# Sprint 48 high-search review

Read-only search review. No game, build, GPU probe, or seed use occurred.

## Recommendation

Run one bounded exploratory screen with **PUCT, 1,600 simulations, depth 16,
world pool 0**. This isolates the higher budget and fresh public
determinizations. Keep the current PUCT constants and MPS inference setup. Do
not spend this screen on depth 32: depth is a per-simulation ply ceiling, and
the tree stops at the first new public state after it expands that node. With
roughly 20 legal actions per position and 1,600 simulations, most paths should
expand near the root. No current receipt records how often depth 16 binds, so
depth 32 has no evidence-led benefit. It can only add work on repeated or
narrow paths. Native actions each advance one turn (`native_environment.rs:464-466`);
the search decrements depth when the turn count changes
(`neural_search.rs:651-659`).

If PUCT gives a useful result and time remains, compare **Gumbel, 1,600,
depth 16, world pool 0, root cap 32** on a new exploratory master. Keep all
other settings fixed. The Gumbel root applies sequential halving to the
considered actions (`neural_search.rs:486-557`). Cap 32 should include all
legal actions in ordinary states near the measured mean; prior canonical
target audit measured 20.89 mean legal actions
(`research/training_strategy/second-development-target-audit.json:37`). It
does not guarantee coverage in states with more than 32 legal actions. This
tests root allocation against PUCT. Do not combine it with depth 32.

Use a 128-game exploratory screen first, not a final screen. Earlier native
results for the same E56 checkpoint moved from 23.2% credit at PUCT128 to
37.775% at PUCT800, both at depth 16 and world pool 3. The masters differ, so
this suggests that extra search can help; it is not a paired estimate of the
budget effect (`benchmarks/strength/native/e56-frozen/screen/summary.json`;
`benchmarks/strength/native/e56-frozen/higher-search/summary.json`). The
800-search run completed 2,000/2,000 games and used 44.8M simulations. It
still lost to the unchanged AlphaZero profile. Treat higher budget as a
worthwhile screen, not a strength promise.

## Determinization and cost

`world_pool > 0` samples that many complete hidden states once at the root,
then cycles them across simulations. `world_pool = 0` calls `determinize` for
each simulation (`neural_search.rs:754-765`; Gumbel uses the same branch at
`neural_search.rs:521-536`). The tree key is the public observation, not the
hidden deck (`environment.rs:127-129`; `native_environment.rs:286-298`). A
three- or eight-world pool can therefore make each move's estimates depend
too much on a small, repeated set of hidden deals. Fresh sampling should lower
that finite-sample effect at 1,600 simulations. It does not remove strategy
fusion or other determinization bias: the tree still merges public states
whose hidden worlds can differ. Fresh sampling also adds one hidden-state
sample per simulation, so it raises CPU work. With 16 workers, watch the game
workers and service queue; do not assume that MPS is the only limit.

The current MPS service log for `external-00` records 449,547 calls in 540.08
seconds, with mean batch 7.33 at the end. The 128-game trial took 531.9 seconds
at Gumbel128/depth16/pool3, eight game workers
(`local/research/sprint48/external-00/service/service.log`;
`research/sprint48/RESULTS.md:39-56`). Scaling its observed calls by 12.5 gives
about 5.62M service calls for 128 games at 1,600 simulations. At the measured
average rate of about 832 calls/second, this is about 1.9 hours. The same
rough rate gives about 29 hours for 2,000 games. These are planning estimates,
not hard bounds: 16 workers can improve batch fill, while fresh
determinization, model change, and shared-host load can reduce throughput.
Reserve about four hours for a 128-game screen (1.9-hour projection plus about
two hours of margin). Re-estimate from the first shard's service-call rate
before reserving a 2,000-game run.

The 800-search Rust model run at eight workers took 836 seconds for 2,000
games (`higher-search/summary.json`). Do not use that wall time as an MPS
service estimate. It used a different inference path and its rate is not
transferable to the current queued MPS service.

## Live-trial addendum: refill chance and worlds

The live PUCT1600/depth32/pool0 trial uses fresh hidden-card partitions, not a
fixed shuffled deck order. `determinize` removes known cards, shuffles the
unknown cards by tier, and splits them between the opponent's blind reserves
and the remaining deck (`crates/splendor-agents/src/native_environment.rs:199-219`).
The deck is an unordered bit set. Each buy, market reserve, or blind reserve
draws a random card from its current tier set, removes that card, and updates
the public count (`native_environment.rs:345-370,401-425`). The environment
calls native apply with no fixed chance seed (`environment.rs:121-125`), so
refills remain stochastic even when `world_pool` is 3 or 8.

At each real move, PUCT pre-samples `world_pool` states and cycles through
clones of those same hidden partitions. Pool zero instead samples a new
partition for every simulation (`neural_search.rs:754-765`). This changes
which unseen cards are assigned to already-existing opponent blind
reservations, and which remain in the deck. It can widen refill support when
the root observation contains such reservations. If it contains none, each
world has the same remaining deck set, so pool zero does not add refill-card
support at that root. In both cases, each `draw` remains random. Pool zero may
therefore widen public chance branches and spread visits across more market
states when hidden reservations affect the deck, which can make the depth cap
bind less often. It gives no such guarantee; search returns at its first
unexpanded public state (`neural_search.rs:606-619`). Pool three also samples
refill outcomes on every simulation; it does not hold the next card fixed.

Nodes are keyed by the public observation (`environment.rs:101-129`). Native
observations contain public market slots and remaining counts, and hide the
deck partition and the other player's blind card identities
(`native_environment.rs:286-298`). Search therefore merges values from
different hidden partitions at the same public state. Pool zero gives those
values broader partition coverage; it does not remove information-set
strategy fusion. It also adds a shuffle/partition operation each simulation.
The current 32-worker trial's reported steady rate, about 4,300 calls/second
with mean batch 31.35/32, supersedes the old eight-worker planning rate while
that load holds. At that rate, the earlier 5.62M-call estimate is about 22
minutes for 128 games, or about 5.7 hours for 2,000 games. Treat these as
steady-state estimates; leave startup, replay, and shared-host margin.

If the live PUCT screen fails, the next controlled search setting is **Gumbel,
1,600 simulations, depth 32, pool 0, root cap 32**, on a new exploratory
master. Keep the candidate checkpoint and every other setting fixed. This
tests whether wider root consideration helps; it keeps the current world and
depth choices constant. Do not increase depth again without recording the
depth-cutoff rate. Preserve a negative result and do not promote the
checkpoint from throughput or dev loss alone.

## Limits

The first recommendation held depth at 16 because no depth-cutoff count is
recorded. The live PUCT trial also raises depth to 32, so its result cannot
separate the effect of depth from the budget and world pool. If PUCT fails,
use the Gumbel comparison above with the same settings. Do not increase depth
again without cutoff evidence. Record configuration and workload hashes.
Keep the AlphaZero checkpoint and 800-simulation opponent unchanged. Do not
use exploratory seeds for final confirmation.
