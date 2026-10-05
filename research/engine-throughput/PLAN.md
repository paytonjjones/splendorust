# Canonical engine throughput plan

Start: 2026-10-05T16:10:20.462742+00:00
Finite budget: 6 elapsed hours, at most 3 implementation branches, 45 CPU minutes
of timed replay, and 90 minutes reserved for checks, independent review, and delivery.
No GPU jobs. One owner schedules builds and timing; Luna helpers do bounded work.

Hypothesis: the baseline pays for complete enumeration, a membership scan, and
direct validation on each internal decision. Stack action-buffer initialization
and repeated payment enumeration may dominate. This is not yet a measured finding.
Profile Rust and C++ before changing production code. Measure phase-specific
legal generation, membership, checked transitions, and traversal/clone overhead
with barriers. Component microbenchmarks are diagnostics, not additive proof.

Keep the restored original harness and seed 424262 as the baseline. Add named
profiles for changes. Compare complete-turn throughput with full enumeration
included; cheaper supplied-action paths are separate diagnostics. Preserve all
canonical actions, their order, and checked-apply behavior. Check state, observations,
events where applicable, outcomes and hidden decks outside timed loops.

Explore up to 32 fixed setup seeds starting at 424262; retain every failure.
Freeze at least four complete traces before final timing. Include different
purchase rates and return/noble counts. Use 7 repeats of 100,000 games per trace
for final timing, with both engine orders alternated by run. Record load, sources,
binaries, compiler flags, counts and raw results. Report unsupported C++ choices.
Run pinned fmt, strict workspace Clippy, release workspace tests, and focused
correctness tests. Do not modify frozen AlphaZero assets or other jobs. Push
validated changes to remote main without force after checking its current head.

## Branch 1: enumeration

Both pre-change profiles completed before production edits. Seed 424262 has
68 main, 46 payment, two return and one noble decisions. Rust median component
costs: main40.8ns, payment19.5ns, return37.4ns, membership2.36ns. Checked replay
without enumeration is1.119us/game; complete list replay is5.242us/game. C++
predecoded full-mask+checked-apply is2.353us/game; original replay is2.650us/game.
C++ main-mask generation is14.4ns. Component timings use different cached
layouts and are not an additive wall-time decomposition.

Hypothesis: precomputed distinct-token take tables, shared affordability inputs,
and guarded payment recursion shortcuts cut the dominant generation work while
keeping every action and its exact order. Budget: 45 implementation minutes,
three short measurement passes, then correctness and multi-trace confirmation.
Keep the original generation as an explicit reference benchmark path.

## Branch 2: bulk token actions

Hypothesis: bulk copies of precomputed ordered TAKE arrays remove per-action
mask assembly and capacity checks. Budget: 20 minutes and one short screen.
This branch passed the same ordered tests. It measured 3.176us/game versus
5.291us reference; main enumeration fell to21.9ns. It still misses C++.

## Branch 3: shared affordability and validated decisions

Hypothesis: for zero-gold states, intersect five precomputed card-cost bitsets
once rather than compare five costs for every candidate. A state-borrowing
Decision can validate membership in its freshly generated complete action list
and reuse that proof for the transition. The exclusive borrow prevents stale
or changed lists. Existing supplied-action apply retains direct validation.
Budget: 30 implementation minutes, two short screens, then final checks and
fixed-suite evaluation. Keep root actions crossing determinizations checked.
No fused turn or restricted payment policy is needed. The full enum+checked
profile remains beside the named full enum+validated-decision profile.

### Branch 3 second screen: action storage layout

The first branch3 screen reached349.9k games/s; C++ predecoded reached395.3k.
Zero-gold cost bitsets did not improve main-generation time in this screen.
The remaining list writes use a seven-byte, byte-aligned Action value. Hypothesis:
eight-byte alignment lets the compiler use one word copy per action rather than
several narrow stores. This changes in-memory layout only; canonical wire tags,
choices, ordering, hashes by fields and replay semantics remain unchanged.
Budget: 20 minutes, one short screen, required tests and the already fixed suite.
Keep the first branch3 receipt as a negative/insufficient result.

## Bounded follow-up after the first fixed-suite failure

The first seven-repeat suite missed predecoded C++ on three of four traces
(Rust/C++ throughput ratios 0.956, 0.888, 0.940, 1.010). Preserve this negative
confirmation and the frozen source receipt. Extend the branch count by one,
within the original six-hour and 45 CPU-minute budgets: at most 45 minutes
of implementation and two short screens, then one fixed seven-repeat suite.
Hypothesis: small cross-crate Decision wrappers prevent useful specialization.
First test inlining alone. If insufficient, test the existing safe index path,
which checks a selected index in the freshly generated complete list. It must
serve real index-selecting callers, preserve action choices and selection order,
and remain a separately named profile beside action selection. Do not claim
that the still-slower action-selection path closes the gap.

The wrapper-only screen matched/exceeded C++ medians on all four traces, with
ratios 1.072, 1.005, 1.060, 1.121. Inlining the large transition helper made
all four slower (0.923, 0.910, 0.938, 0.963). Revert that change, retain its
source and logs, and confirm wrapper-only code on the unchanged fixed suite.
No index-only workload or caller contract change was needed.

The second confirmation passed all four medians, but host load changed from
6.9 to 34.1 during its command sequence. This is a material source of timing
uncertainty. Repeat the unchanged suite in reverse seed order, which reverses
the Rust/C++ order for every trace. Use the same 100,000 games and seven repeats,
within the original time/CPU budget. No production code or profile contract
changes. Require both confirmations to pass; retain the first and all failures.
