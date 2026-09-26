# Validation and rule decisions

## Scope and authority

The implementation follows the publisher's base-game rules. The complete functional datasets are documented in [data/SOURCES.md](data/SOURCES.md). There are no expansions or copyrighted visual assets.

Tests cover setup for 2/3/4 players, each main action, bank exhaustion, double-take threshold, optional gold use, discounts, free purchases, reservations and the three-card cap, market refill/deck exhaustion, token returns, one noble per turn, noble choice, end-game timing, fewest-card ties, and shared victories.

The core property test branches over **every** generated legal action at each sampled state, applies it to a clone, and checks invariants. It also reconstructs hidden worlds and checks that the original observation is preserved. Independent Cartesian reference enumerators check the optimized payment and return generators. Invalid indices, payloads, and observations are tested for rejection without state mutation or panics. Observation validation rejects an opponent blind-reservation identity supplied by a caller, as well as inconsistent reservation counts. Such an identity cannot occur in the canonical redacted observation.

Invariants check the complete 90-card partition, every card's tier/location, compact reserved slots, all six token totals, hand limits including pending returns, derived score, derived bonuses, noble ownership/eligibility, and phase constraints. They also check seat/turn consistency, mandatory market refill, and a threshold score for a declared final round. All tokens, including gold, are conserved. Setup determines the total supply.

Reproducibility tests cover RNG golden values, seeded transitions, hidden-information redaction, agent choices, replay serialization, and identical serial/parallel game records. The test suite runs 10,000 seeded random trajectories with invariants after every decision. A separate large release audit is recorded in [docs/results/million-audit.txt](docs/results/million-audit.txt).

## No-action positions and nontermination

A reproducible random trajectory reaches a position with an empty colored bank, three active-player reservations, and no affordable card. Gold can remain in the bank, but it cannot be taken without reserving. This is a rules gap, not a negative-token or missing-card failure.

The printed rules do not define a forced pass or stalemate winner. We therefore stop and label the trajectory `no_legal_action`. We do **not** classify that position as a normal terminal state, award points-based wins, or silently drop it from comparison uncertainty. An all-random arena reaches these positions frequently. A regression test also shows that legal take-and-return turns can repeat forever. Thus, termination is a measured property of a policy/seed set, not a theorem about all legal play.

Normal-game results, no-action counts, and decision-limit counts must be reported separately. The promotion gate rejects a candidate when any game is unfinished. A future optional forced-pass ruleset would need its own version and experiments. It must not silently change this ground truth.

## Interpretations

- Take three distinct colors when at least three piles are available. Take fewer only when fewer colors remain. The newer publisher rules state this explicitly.
- Return exactly the excess above ten. Old or newly taken tokens, including gold, can be returned. No voluntary return below ten is added.
- Gold can replace a matching token that the player already has. All such payment choices are enumerated.
- Visible reservations remain known; blind reservations reveal only tier and count to other agents.
- Nobles use permanent bonuses only, do not consume them, and are mandatory. If more than one qualifies, the player chooses exactly one.
- Exact ties after prestige and fewest purchased cards share victory. Reserved cards are not an extra tiebreaker.
- A player can gain a noble on a take or reserve turn if the requirement was already met.

## Limits of the evidence

No external engine is used as an unquestioned oracle. The pinned MIT-licensed reference matches all 90 card / 10 noble tuples. The development workload and separate tier-depletion histories cover 5,056 matched selected turns and 14,330 shared branch successors. A fresh 60-game confirmation covers 4,949 matched selected turns and 14,342 shared branch successors at 752 positions. Selected and branch cases can overlap; these are not independent game counts. [The comparison record](docs/PARITY.md) defines the workload, checks, exclusions, source, and license. The reference has material rule and information differences. This is bounded transition parity, not full engine equivalence. Earlier data sources include an unlicensed repository; no implementation code from it was copied. The local independent enumerators cover the largest combinatorial decisions.

No test suite proves all reachable states correct. The milestone is a tested foundation with explicit rule boundaries. Search strength has been measured against the included agents, not against expert humans. The core does not yet have a formal verification proof, external engine equivalence certificate, or tested cross-platform floating-point search guarantee.

## Report rerun checks

New reports contain `run_config`, including all search settings and an optional
precise duration. Serialization stays in the arena crate. `verify-report FILE`
requires a matching engine and source fingerprint, fixed budgets, valid run
settings, and agreement between structured settings and existing metadata. It
reruns the tournament and compares ordered game records exactly. Capped and
blocked records can pass this reproducibility check; they still cannot pass the
promotion gate. This command does not verify statistical summaries or timing.
Reports without structured settings remain readable and fail rerun verification
with an explicit error. The same 1,700 fixed-budget game records match on
ARM macOS, x86-64 macOS under Rosetta, and ARM Linux. See
`docs/results/x86-validation.json` and `docs/results/linux-validation.json`.
This bounded check is not a general floating-point portability guarantee.

Tests cover non-default search settings, all rollout/evaluation choices,
nanosecond duration preservation, unknown fields, changed game records,
inconsistent metadata, missing settings, source/version mismatch, timed runs,
and exact reproduction of capped records.

## Promotion evidence checks

The promotion gate validates ordered game records and structured settings before
it accepts a stage. It checks the requested agents, game count, seed, thread
count, fixed search budget, and the setup seed schedule retained from version 1. Engine and source
identity must stay the same between screen and confirmation. The CLI arguments
state the depth, width, rollout policy, evaluation, and decision cap explicitly.

The gate recomputes the candidate interval from independent setup blocks and
uses that interval for decisions. A supplied interval that differs beyond
floating-point tolerance is rejected. Shared wins retain fractional credit;
unfinished outcomes retain bounds of zero and one. Throughput must agree with
elapsed time and requested games. These checks establish report consistency;
they do not replace engine validation or prove that an arbitrary report is a
true record of executed games.

New run manifests and final decisions record SHA256 hashes of `promote.py` and
`collect_evidence.py`, in addition to the Rust source fingerprint and raw/record
hashes. Fresh promotion stages require structured settings. Historical archives
remain readable and are not rewritten to claim checks that did not run.

## Historical validation records

The sections below record checks at the time of each change. Engine versions and
test counts in those records are historical unless explicitly marked current.

## Observation round-state consistency

Determinization now rejects two inconsistent input states that previously passed
structural checks: threshold prestige with no final-round flag in an ordinary
main phase, and a completed final round relabeled as a main phase. A legal
pending multiple-noble choice is different: the actor can have reached 15 points
before the turn ends, with the final-round flag still false. That state remains
valid for every viewer, and every legal noble choice remains available.

The version-1 `threshold-noble-v1.json` replay reaches this boundary after 228
legal decisions in a four-player game. Tests preserve that valid state and reject
its malformed variants. The completed seed-42 replay tests the terminal restart
rejection. These checks do not prove that every accepted observation is reachable.

All 5,470 turn records and their sampled choice snapshots remain byte-identical
to the prior winner audit, excluding the changed source header. A fresh invariant
audit requested 100,000 games; complete seat-block rounding produced 99,997:
89,101 normal completions and 10,896 blocked games with no winner. The command,
source fingerprint, counts, and hashes are in `docs/results/threshold-validation.json`;
stdout is in `docs/results/threshold-audit.txt`. No valid rule, RNG, enumeration,
or replay behavior changed, so the engine remains `splendorust-v1`.

## Validation workflow coverage

`cargo test --workspace --release --locked` includes the two `block_audit`
example tests through an explicit Cargo target with `test = true`. These tests
check the distinction between a bounded cutoff and a real block, and the
adversarial result for each of five recorded root choices. The standard Rust
suite currently runs 71 tests.

CI fetches the independent reference at the exact commit recorded in
`docs/PARITY.md`, then sets `SPLENDOR_REFERENCE` for Python test discovery on
both operating systems. The comparison loader checks commit, tracked-file
cleanliness, and license before importing the rules. No external ML packages
are installed. Fetch or validation failures fail the workflow rather than
silently skipping the reference tests. The 56 Python tests include 28 reference
tests; local runs without `SPLENDOR_REFERENCE` explicitly skip those 28.
A fresh checkout and all 29 tests passed locally when this workflow was first added.
Hosted Linux/macOS workflow results are not yet verified.

Two additional legal four-player histories cover tier 2/3 final draws and both
purchase and reservation after deck exhaustion. All 589 shared branch successors
match the pinned reference; one selected return path remains excluded under its
known rule difference. See the high-tier history evidence in [docs/PARITY.md](docs/PARITY.md).

The parity harness separately checks local reservation visibility and ordered
slot preservation, including branches excluded from external rule parity. The
reference does not implement matching private-information masks.

## Final-round trigger seat order

A nonterminal final round must have been triggered by a threshold player in an
earlier seat of the same round. An unplayed seat cannot already have 15 points:
that score would have ended the previous round before seat zero played again.
The current actor can newly reach 15 during a pending noble choice; that score
does not set the final-round flag until the turn finishes. An earlier threshold
player may already have set it.

The validator now enforces these ordering constraints. Two malformed states
were reproduced as accepted before the fix: a prematurely flagged pending noble
choice, and an ordinary Main phase with the current actor already at threshold
even though an earlier seat was a valid trigger. Regression tests also reject a
threshold in a later seat while preserving real pending and completed turns.
The tests use legal histories, including the three-player 16/16/14 finish at
seed 95,000,017, then change only observation fields to construct the bad input.

All 58 release Rust and 37 Python tests pass, with formatting and strict workspace
Clippy. A fresh seed-108,000,000 invariant audit checked 99,997 games after seat
rounding: 89,068 completed and 10,929 blocked, with no capped winner or invariant
failure. All 5,511 selected case lines and their sampled branches in the three
current parity workloads are byte-identical after removing source metadata.
See `docs/results/round-order-validation.json` and the saved audit/reproduction
logs. ENGINE_VERSION remains `splendorust-v1`: only malformed-observation
acceptance changed; valid rules, action order, RNG, and replay semantics did not.

Search rollout depth uses elapsed turns, so a large requested depth cannot
wrap an absolute `u32` turn deadline. The regression covers a legal nonzero-turn
position and eight fixed agent seeds. Core counter exhaustion is handled separately by the v2 resource-limit
contract described below. See the search depth audit in EXPERIMENTS.md.

The public arena `play_game` entry point validates `RunConfig` and requires
`rotation < player_count`. Invalid counts (including values that truncate when
cast to `u8`), invalid run settings, and extreme rotations return errors before
play. `block` remains a caller-supplied record label. A direct-call regression
checks all seats for 2/3/4 players against tournament records, including capped
games with no winners or ranks. Tournaments validate once before their workers
call the private game runner.

### Confirmed v1 turn-counter boundary defect

`turn_limit_audit` first replays `return-cycle-v1.json` and checks a full legal
cycle restores its observation except for two completed turns. The cycle uses
only Take and Return, so hidden decks and card ownership stay fixed. Repeating
that cycle 2,147,483,617 times advances the recorded turn 61 to `u32::MAX`.
The audit skips those identical cycles by changing only the public turn count,
then reconstructs a valid hidden state. It does not claim to replay billions of
turns or preserve the original hidden deck order.

The next legal Return reproduces two distinct failures at current v1:

- Debug panics after changing tokens, leaving an invalid Return phase.
- Release accepts the action, wraps turns to zero, and passes invariants in
  this two-player state.

Neither produces an outcome. Raw results and stderr are archived in
`docs/results/turn-limit-{debug,release}.{json,stderr}`. Reproduce with:

```sh
cargo run --locked --example turn_limit_audit
cargo run --release --locked --example turn_limit_audit
```

This was confirmed in v1 and is fixed by the v2 contract below. Widening
the counter alone would only move the defect to a larger limit. The ordinary
arena decision cap does not prove all direct core callers stay below the boundary.


### Version 2 resource-limit contract

`ENGINE_VERSION` is `splendorust-v2`. At `turns == u32::MAX`, a rules-legal
`apply_action` returns `RuleError::TurnLimit` before mutation. Illegal actions
still return `IllegalAction`. Legal enumeration remains unchanged: capacity
is an implementation limit, not a published rule or a victory. All decision
phases use the same guard. A turn starting below the limit can reach the limit
and can end the game normally. Terminal outcomes remain available at the limit.

Search evaluates a truncated rollout at capacity with its existing nonterminal
evaluation. At a root already at capacity it selects the usual heuristic legal
action; the caller receives the core resource error. The arena propagates that
error and cannot present the failed run as a complete promotion result.

Old v1 histories are retained unchanged and rejected by the v2 replay loader.
The ten `*-v2.json` golden fixtures copy only the engine label; tests replay
and check their unchanged actions and snapshots. Hashes and semantic-copy
checks are recorded in `docs/results/capacity-validation.json`. Use the original
v1 commit to replay old reports or histories; do not silently relabel evidence.
The promotion stage validator now requires v2 and tests reject v1 stage input.

Both debug and release boundary audits return TurnLimit with unchanged state,
valid invariants, and no outcome. New tests also check every legal action in
all four decision phases, search near/at capacity, and an actual final turn
that reaches the limit and keeps its correct outcome. All 68 release workspace
Rust tests and 37 Python tests pass. The fixed 1,000-game search/strong comparison
at seed 110,000,000 has identical complete game records before and after.

### Historical report handling after v2

The archive collector accepts historical report schemas and preserves their
engine/source fields. New index entries include `engine` and `source_id`; a
missing historical source is recorded as null, never inferred. Existing index
entries are retained unless their corresponding raw report is processed again.
The standalone promotion decision and the full stage validator share a v2
engine/source-presence check. The full workflow still checks settings, seed
schedule, record consistency, and source consistency across stages.

An audit of all 49 archived raw reports (48 v1, one v2) preserves their identity
and permits historical summarization. Seventeen old reports have no source
fingerprint. None of those identities is filled in or relabelled. The current
decision helper rejects all v1 reports. `verify-report` rejects the archived
v1 capacity report and reproduces all 1,000 records of the matching v2 report.
Audit identities, raw hashes, tool hashes, and CLI output are in
`docs/results/version-tools-*`. These checks do not certify old reports as
current-build experiments. Both added regression tests failed before the fix;
all 39 Python tests now pass with the pinned independent reference.

### Local tests for excluded reference rules

The optional-gold transition test now starts with a real dealt card and a
conserved token supply. It checks all 16 colored/gold payment subsets for card
0, including all gold, for both market and reserved purchases: 32 complete
purchase branches. Each branch checks bank/hand changes, ownership, bonus,
reservation removal, turn advancement, no outcome, and full invariants. This
supplements the independent Cartesian payment-generator test and the existing
invalid-payment tests, whose manually replaced market is not a valid full state.

A second valid-state test owns seven cards of one bonus color, purchases an
eighth, and checks the complete partition and token invariants. The reference's
seven-card cap is still excluded explicitly; local success is not external
agreement. Existing return tests already apply every generated excess return
with invariants, including old, newly collected, and gold tokens. No rules,
actions, or agent behavior changed in this coverage addition.

### Validation after target-cache performance changes

E14/E15 preserve cached versus original scores across all legal actions in
96 seeded 2–4-player trajectories, including all four decision phases. Fresh
invariant-enabled search/strong comparisons at 128/8/6 include 300 three-player
games (118m) and 400 four-player games (119m). Every game completes; before and
after records, including trajectory hashes, match exactly. Reports and commands
are retained in `docs/results/e15-multiplayer.json` and referenced archives.

Re-exported the existing 60-game independent-reference workload (111m master)
after both optimizations. All 5,370 case payloads are byte-identical; only source
metadata changes from `5fbacedf05ec987b` to `50400f40eb161b1a`. The pinned MIT
reference check again matches 4,949 shared selected successors and 14,342
sampled shared branch successors. Known exclusions, three blocked games, and
reference winner defects remain unchanged. This is regression validation on
existing seeds, not a new independent sample or full parity. Exact commands,
hashes, archive reconstruction and checker output are retained in
`docs/results/reference-e15-validation.json` and `reference-e15.summary.json`.

### Local second-architecture validation

At source `50400f40eb161b1a`, installed the pinned Rust 1.98.1
`x86_64-apple-darwin` target and ran release workspace tests and build with
Cargo.lock. All 71 tests pass under Rosetta on the Apple M4 Pro/macOS 26.7 host.
This includes golden replays, rule tests, and search determinism tests.

The x86_64 CLI's verify-report command reproduces every record from the ARM
build's 1,000 two-player games (1,117m), 300 three-player games (118m), and 400
four-player games (119m). Settings are search/strong at 128/8/6; the multiplayer
runs enable invariants. All 1,700 games complete, with exact record and
trajectory-hash agreement. Timing and report summaries are not compared.
Commands, input and binary hashes, process results, test/build logs are in
`docs/results/x86-validation.json` and `x86-*.txt`.

This establishes agreement for those workloads and two macOS CPU targets under
one toolchain. Rosetta is not a physical Intel host or a Linux environment.
Hosted CI and a universal floating-point search guarantee remain unverified.

### Local ARM Linux validation

At source `50400f40eb161b1a`, Rust 1.98.1 on `aarch64-unknown-linux-gnu`
passes formatting, strict release workspace Clippy, all 71 release Rust tests,
and all 46 Python tests with the pinned independent reference. A Docker Desktop
ARM Linux VM uses the official Rust image pinned by digest
`sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e`.
Source and reference mounts are read-only; build output is separate.

Linux verify-report reproduces all 1,000 two-player, 300 three-player and 400
four-player records used in the x86 macOS check above, including trajectory
hashes. All games finish. This checks these fixed budgets and seeds across
native ARM macOS, x86 macOS under Rosetta, and ARM Linux. It does not prove
all-platform floating-point equality or replace a hosted CI run.

The first setup attempt exited before testing because the linked worktree's
Git file referenced a host-only path. A source snapshot without that link fixed
the container setup. The failed attempt and successful test/build/verification
logs are retained in `docs/results/linux-*`; `linux-validation.json` identifies
the source, image, binary, input hashes, commands, mounts and exit statuses.

### Promotion executable provenance

The gate builds the named arena binary with Cargo JSON output and selects the
reported executable. It no longer assumes `target/release/splendor`, which can
be stale when CARGO_TARGET_DIR or a configured target changes the output path.
It rejects failed builds, missing executables, and ambiguous executable reports.
Each run now retains `cargo-build.jsonl` and `build.json` with the exact selected
path and binary SHA-256. Source and report validation still apply separately.

A regression test failed against the old hard-coded path. The fixed gate passed
all 48 Python tests. An actual custom-target run also passed required Rust checks
and used `/private/tmp/promotion-custom-target/release/splendor`. Two-game screen
and confirmation stages correctly returned `retain baseline: benefit not
confirmed` (exit 2). This smoke is not strength evidence. The separate random
benchmark reported eight blocked games without inventing winners. Commands,
logs, Cargo artifacts, and reports are in `docs/results/promotion-target-*`.

## Export workload sequence checks

The reference harness now checks each full export against its declared setup
seed and policy schedule. Each game starts at turn zero. Every next `before`
snapshot must equal the preceding selected `after` snapshot. The game count
and order must match the header. A game ends at a normal finish, an explicit
blocked record, or the exporter's 1,000-turn cap. Blocked and capped games
receive no winner from this check.

Tests reject missing, duplicate, reordered, truncated, and changed snapshots,
wrong seeds or policies, and missing or conflicting workload scope metadata.
The separate depletion-history exports do not declare a full-game schedule;
the report explicitly marks this sequence check as not applied to them.

Both archived 60-game workloads pass the new check, as do their existing
transition and branch checks. All four archived input files were checked again;
no new seeds or trajectories were generated. The new results are
`docs/results/reference-v2-sequence.summary.json`,
`reference-confirm-v2-sequence.summary.json`, and the corresponding
`reference-v2-tier2-sequence.summary.json` / `reference-v2-tier3-sequence.summary.json`.
All 54 Python tests pass with the pinned reference. These are local export
continuity checks, not chained external-engine trajectory parity. Rust and
engine semantics are unchanged.

## Retained external-state segments

`check_reference.py --chains` now carries the external successor across
consecutive shared turns. Before each turn it compares the retained state
with the next local snapshot. It aligns only the exogenous replacement draw;
it does not replace tokens, player cards, scores, nobles, or market state.
An explicit rule exclusion ends the segment. A new game or a later shared
segment starts from a snapshot. The ordinary isolated-turn checks still run.

The development archive passes 5,016 turns in 433 segments, with 27 complete
games from turn zero to normal termination without a state reset. Its longest
segment has 108 turns. The confirmation archive passes 4,949 turns in 427
segments, with 30 complete games without a reset and a longest segment of
112 turns. Tier 2 passes 16 turns in one segment; tier 3 passes 24 turns in two
segments. All four `*-chains.summary.json` files record segment histograms,
explicit break counts, and the seeds of complete games without resets.

The tests confirm one hydration per segment and reject corrupt retained bank
state. All 56 Python tests pass with the pinned reference. These checks reuse
the archived workloads; they are not new independent confirmation games.
The reference winner defect is still checked as a known difference. This is
stronger evidence for shared transitions over time, not full rule, RNG, deck
order, observation, or winner parity. No engine or Rust code changed.
