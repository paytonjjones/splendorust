# External benchmark baseline — 2026-09-29

This report ranks only workloads with checked equivalent behavior. The full
published-rule Splendorust workload remains a native baseline. A restricted
whole-game profile and a checked opening operation permit comparisons with the
public C++ reference. No unrestricted whole-game or cross-engine search speed
claim follows. The C++ repository has no license file; it is a public-source
reference, not a verified licensed open-source implementation.

The protocol is [PROTOCOL.md](PROTOCOL.md). The exact whole-game contract is
[PROFILES.md](PROFILES.md). Pinned candidates, licenses, APIs and failed gates
are in [CANDIDATES.md](CANDIDATES.md). Historical `BENCHMARKS.md` measurements and
all failed experiments remain in place.

<!-- measured tables are inserted after final validation -->

## Scope and correctness

The `seal256-intersection-v1` profile injects the same full decks and nobles,
uses functional card/noble mappings, and sorts semantic action keys. Random
selection uses the same rejection-sampled SplitMix64 stream. The fixed policy
has the same buy/take/reserve priorities. Both engines validate selected moves.
The profile has two players and the normal 15-point equal-round finish.

The profile excludes blind reservations, partial exhausted-bank takes and token
returns. It retains the C++ double-take omission at eight held tokens and uses
colored-first payment. A selected purchase with multiple eligible nobles stops
as unsupported. Empty profile choices stop without a fabricated pass or winner.
These restrictions align the measured trajectories; they do not establish all
legal-choice equivalence. Every incomplete case remains in the time denominator.

The smoke gate compares every normalized public state, projected legal-action
set, selected key and outcome for 64 random and 64 fixed cases. Larger timed
corpora compare all normalized final records across engines, worker counts and
repetitions. Full hidden deck order is injected once; it is not independently
compared at each turn. Final-record equality is weaker than a full trace gate on
all measured cases. The report retains both gate scope and record hashes.

Aligned throughput includes native legal generation, profile projection, sorting,
policy, checked transitions, per-game clocks and small result records. It excludes
setup, warm-up, pool startup, final snapshots and serialization. C++ uses minimal
JSON record boxing; Rust uses typed records. That difference is retained and
limits the claim to aligned adapter pipeline throughput. It does not isolate
engine apply or enumeration costs. Native phase counts differ, so common completed
player turns are the comparison unit.

The opening group measures full native state clone, checked white/blue/green take,
result consumption and destruction. It excludes legal enumeration and setup.
Native state sizes and clone ownership differ. Rust uses a persistent Rayon pool;
C++ excludes warmed thread creation but includes release/join. One-thread results
are the primary comparison. Opening speed does not imply complete-game speed.

## Rules alignment and policy repairs

The merged three-player fix is PR [#1](https://github.com/paytonjjones/splendorust/pull/1).
The two-player fix changes Search and Strong choices using public sufficient
conditions. It fixes four retained blocked histories and preserves unknown blind
reservations. Core rules, legal actions, RNG and replay behavior remain version 2.
Search rollouts keep their original scoring. An independent review also checked
last-seat noble completion before accepting the final guard.

The fresh E21 screen and confirmation gates contain 70,000 completed Search/Strong
games across two, three and four players, with fixed 128/8/6 budgets. E22 corrects
the last-seat noble boundary. Its same-seed reruns check that all ordered records
remain unchanged; these reruns are not fresh holdouts. The baseline uses the
corrected E22 source. These gates
are conditional on their policies and seeds; they do not prove termination for
all legal play. [Policy evidence](../docs/results/two-player-policy/README.md)
includes the rejected E20 candidate, full reports and regression histories.

A separate Search32 self-play diagnostic has 293/300 completed two-player games,
298/300 three-player games and 298/300 four-player games. Seven two-player cases
reach a verified four-decision token cycle. Four other cases block due to a blind
reservation, a purchase outside the take guard or a sole legal take. All eleven
unfinished histories have no winner. They remain documented references. The
primary search workload uses Search128 in seat zero against Strong in other seats.
It records actual simulations and includes opponent and fallback decisions.
Native greedy includes deterministic local scoring and Observation costs. It is
an AI-policy baseline, distinct from common aligned fixed-policy throughput.
Native random play uses uniform legal choices without AI evaluation or search.

Optional `benchmark-compat` APIs inject complete validated setups and expose an
explicit experimental no-action pass. The measured profile does not use that pass.
It cannot pass when a published legal action exists; a full no-action cycle cannot
produce a stalemate winner. Normal rules and replays remain unchanged. Reports
using this hook must name `splendorust-v2-benchmark-compat-v1` and their exact profile.

## Confidence, references and remaining gaps

Each baseline row retains every repetition and an interval for the median timing
rate from 10,000 deterministic bootstrap samples. These intervals describe local
repetition noise, not game-rule validity, policy strength or performance on other
hardware. Short windows retain a preliminary label. No core affinity, frequency
lock or dedicated host was used. macOS uses a mix of performance and efficiency
cores; background work and scheduling can change rates and scaling.

Native per-game latency comes from a separate instrumented probe. It includes
setup and play but excludes queue wait, final digest and destruction. Its random
latency percentiles pool completed and unfinished trajectories; they are not
completed-game percentiles. Aligned latency clocks are inside the pipeline and
are split by completion status. Batch time divided by game count is not a latency
percentile. Installation/build costs may reuse caches and are not cold-install
estimates. Process wall time includes work excluded from steady-state clocks.

The Numba opening reference verifies fixture results but its timed apply helper
is unchecked. Compiled one/four-thread and public Python API measurements stay
unranked. Import, JIT and startup costs are separate. Upstream decorators retain
their pinned optimization flags. Roeey's tiny trace prefixes match, but its
seven-bonus cap and mandatory copied action history exclude a speed ranking.
Splendimax and Go build; concrete transition/rule defects exclude them. Lapidary
has different rules and hidden-information access. The original AlphaZero source
was audited without a runtime measurement. Java and JavaScript references have
standard-card data mismatches. Unsupported results are not zero-throughput rows.

The largest gap is a licensed second implementation with equivalent unrestricted
legal choices, complete setup injection and retained whole-game traces. There is
also no cross-engine search comparison: MCTS, root UCB and depth search perform
different work, even at equal iteration counts. Multihost timings, larger full
trace gates and isolated checked-transition corpora are still needed.

The next benchmark step is to extend the licensed Numba engine's adapter with
verified full fixture conversion, projected choices, explicit unsupported/pre-cap
stops and a checked transition interface. The feasibility probe already verifies
all ninety scheduled native draws without a source patch. Then verify a named
whole-game profile. Keep any upstream interface patch minimal
and recorded. Separately, add late-game checked fixtures for payment, returns,
reservations and nobles. Those fixtures can identify which engine operations
need engineering work before making a broader speed claim.
