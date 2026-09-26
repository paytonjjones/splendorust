# Independent engine comparison

Checked on 2026-09-25 against `roeey777/Splendor-AI`, commit
`95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b`:
https://github.com/roeey777/Splendor-AI/tree/95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b

The checkout has an MIT license (copyright 2024 roeey777). The harness checks the
commit, tracked-file status, and license before import. It records the license
SHA-256. No external implementation code is copied into this repository. The
optional audit imports the reference rule modules from a separate checkout.
It needs only Python's standard library; it does not install or import the
reference's ML dependencies.

## Checked scope

The functional data matches all 90 cards and all 10 nobles after color and ID
normalization. For each sampled complete turn, the harness constructs the
reference state from a privileged test snapshot, checks that the compound
turn is in the reference legal-action list, applies it through `update`, and
compares tokens, purchased and reserved cards, bonuses, points, nobles, market,
deck counts, next seat, and normal end timing.

The reference draws from independently shuffled decks. The harness aligns the
single replacement draw before a turn. It does not compare RNGs or assert that
unknown deck orders match. State construction uses each player's own observation
to recover private reservations for the test. This data never goes to an agent.
The harness compares a turn in isolation; it does not feed one reference result
into the next case. Thus the result is transition parity on the stated shared
cases, not full engine equivalence.

The first fixed workload uses 20 games per player count (2, 3, 4), alternating
strong and random policies, seed 92,000,000 plus player count times 1,000,000
plus game index. Each game stops at normal termination, a blocked state, or
1,000 complete turns. The exporter does not award wins to stopped games.

Result: **5,016 matched turns**, including **130 noble acquisitions** and
**52 normal end transitions**. Exclusions: 90 blind reservations, 298 returns
of a collected color, and 64 optional gold payments. These are counted, not
silently removed. The summary includes source, exporter, harness, license,
and case-file identifiers. The compressed cases preserve the exact inputs.

## Complete action sets

A second export of the same workload enumerates every complete-turn path at
every tenth turn, plus each blocked position. This includes payment, return,
and noble branches. After explicit rule-difference filters, both engines have
exactly the same **10,258 shared choices at 574 positions**. Two of these
positions have no local legal action; the reference offers a pass.

The local exclusions are 981 blind reservations, 288 optional gold payments,
and 5,046 returns of a collected color. The reference exclusions are 2,257
reduced takes and two passes. Counts refer to compound turn paths, so several
paths can start with the same main action. Duplicate shared paths fail the
check. Missing or extra shared choices also fail it. The seven-card limit is
an explicit filter but was not reached in this workload.

Evidence: `docs/results/reference-choices.summary.json` and its compressed
case file. Use a third exporter argument of `10` to reproduce this sampling.
An argument of `1` checks every visited position; `0` disables regular
choice sampling. Blocked states always include their empty choice set.
The optional tests also inject missing and duplicate choices.

## Differences and limits

The publisher's refreshed rules remain the rule authority:
https://cdn.svc.asmodee.net/production-asmodeeca/uploads/2022/01/SCSPL01EN_SPLENDOR_RULES_LIGHT.pdf

| Area | Reference behavior | Local behavior / audit scope |
|---|---|---|
| Blind reservations | No action | Supported; excluded from shared-turn check |
| Gold payment | Uses colored tokens first | Preserves optional gold use; those payments excluded |
| Token returns | Cannot return a collected color | Preserves every excess-return choice; those returns excluded |
| Reduced takes | Allows smaller takes near the hand limit | Local takes follow available-pile count; Shared full-turn choices checked after explicit filters |
| Bonus count | Blocks a purchase at exactly seven cards of that color | No such local cap; excluded if encountered |
| Nobles | Includes a choice in each compound action | Local pending phase or automatic single choice; compared after complete turns |
| No legal action | Adds pass, ends when all pass | Local engine reports unresolved rules gap, with no winner |
| Tiebreak | Minimum cards computed over all players | Local minimum is among tied leaders; winner differences classified explicitly; lower-place ranks not compared |
| Information | Full state and decks exposed; no private-information mask | Local agents receive redacted observations; information parity not claimed |
| Invalid actions | Successor assumes valid input | Local validation rejects invalid actions; error parity not claimed |
| RNG and replay | Different setup and history representation | Not compared |

An external engine can share a defect with the local engine. This comparison
supplements the publisher rule audit, invariant tests, and independent payment
and return enumerators. It does not replace them.

## Reproduce

```sh
git clone https://github.com/roeey777/Splendor-AI.git /tmp/splendor-reference
git -C /tmp/splendor-reference checkout 95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b
cargo run --release --locked --example parity_export -- 20 92000000 > /tmp/parity.jsonl
python3 scripts/check_reference.py --reference /tmp/splendor-reference \
  --cases /tmp/parity.jsonl --output /tmp/parity-summary.json
SPLENDOR_REFERENCE=/tmp/splendor-reference \
  python3 -m unittest discover -s scripts -p test_reference.py
```

The optional integration tests verify matches and exclusions, and ensure that
corrupt scores, bank counts, and deck partitions are detected. Ordinary Cargo
tests stay offline and do not require the reference checkout.

## Encoded-path audit

A mutation of the noble-choice action in setup 94,000,012, turn 45 exposed a
harness defect: the adapter inferred the noble from the successor and ignored
the explicit encoded noble ID. Changing ID 7 to 8 still reported a match. The
harness now checks the encoded ID, required multiple-noble phase, compound phase
order, byte shape, and zero padding. The regression fixture is
`scripts/fixtures/reference-noble-choice.json`, extracted from the archived
choice workload. It also rejects removal of a required noble choice and a
duplicate noble phase. No engine behavior changed.

The stronger check passed all 5,016 previously shared transitions and all 10,258
shared choices at 574 positions, with unchanged exclusions. This is a recheck
with a repaired verifier, not an increase in sampled coverage. Evidence is in
`docs/results/reference-path-audit.summary.json`; its case-file hash identifies
the existing `reference-choices.jsonl.gz` input after decompression.

## Shared branch successors

Export format 2 adds a privileged successor snapshot to every sampled compound
choice. The harness checks the resulting state for each shared choice through
the external engine, as well as comparing the complete shared action sets.
Missing snapshots and corrupt branch scores fail validation. Format 1 remains
readable; no successor claim is made for its alternative branches.

The fixed 60-game workload now matches **10,258 shared branch successors**:
2,650 for two players, 3,167 for three players, and 4,441 for four players.
These include 57 terminal successors, 50 noble acquisitions, and four explicit
noble-choice branches. Some overlap the selected-turn checks; these are not
counts of additional independent games. The 5,016 selected-turn matches and all
exclusion counts remain unchanged. Every selected path and choice signature
was also checked against the prior export and is unchanged.

Evidence: `docs/results/reference-successors.jsonl.gz` and
`docs/results/reference-successors.summary.json`. The engine remains version 1;
format 2 versions the offline audit data, not game rules or replay semantics.

```sh
cargo run --release --locked --example parity_export -- 20 92000000 10 true > /tmp/successors.jsonl
python3 scripts/check_reference.py --reference /tmp/splendor-reference \
  --cases /tmp/successors.jsonl --output /tmp/successors-summary.json
```

The final `true` enables branch snapshots. All earlier scope limits still apply,
including reference rule exclusions, aligned replacement draws, isolated
transitions, and no full outcome or hidden-information parity claim.

## Targeted boundary samples

The fifth exporter argument, `true`, adds choice sampling at every observed
explicit noble-choice turn, terminal turn, and first turn of the final round.
It supplements the regular interval without changing the played trajectory.
The verifier rejects a missing sample at a required regular or boundary position.

On the same 60-game workload this adds 94 positions (28 two-player, 32
three-player, 34 four-player). The combined result is **11,889 shared branch
successors at 668 positions**, including 802 terminal successors, 138 noble
acquisitions, and 16 explicit noble-choice branches: six for two players, six
for three players, and four for four players. These overlap prior checks; they
are not additional independent games. All prior selected paths and sampled
branches were compared and remain unchanged.

The wider boundary coverage also reaches the reference's seven-card purchase
limit once, at setup 96,000,011, turn 135. It remains an explicit rule exclusion,
not a local restriction. A small fixture now tests that difference directly.
Other branch exclusions are 1,103 blind reservations, 324 optional gold payments,
and 5,290 returns of collected colors; the reference excludes 2,461 reduced
takes and two passes. Selected-turn counts are unchanged.

Evidence: `docs/results/reference-boundaries.jsonl.gz` and its summary. Run:

```sh
cargo run --release --locked --example parity_export -- 20 92000000 10 true true > /tmp/boundaries.jsonl
python3 scripts/check_reference.py --reference /tmp/splendor-reference \
  --cases /tmp/boundaries.jsonl --output /tmp/boundaries-summary.json
```

This extends checked choice and transition coverage. The documented outcome,
RNG, information, and rule differences still prevent a full-parity claim.

## Normal-game winner masks

New exports include the actual `GameState::outcome()` winner mask, with
`winner_checks: true` in metadata. Nonterminal snapshots have `null`; a blocked
state cannot acquire a winner. The harness checks the local mask against
prestige and the fewest purchased cards among tied leaders. It also checks
final-round and terminal flags at the exported complete-turn boundaries.
Required masks cannot be omitted from selected or branch snapshots.

For shared normal finishes, the harness calls the reference's `calScore` and
compares the set of highest-scoring players. It classifies a difference only
when a nonleader has fewer cards than every leader, the leaders have unequal
card counts, and the reference incorrectly retains all tied leaders. Other
winner mismatches fail the audit. Copying that incorrect shared result into the
local mask also fails; this is a reference defect, not a local rule variant.

Results on the boundary workload:

| Checked finishes | Winner matches | Known reference tiebreak defect |
|---|---:|---:|
| 52 shared selected finishes | 50 | 2 |
| 802 shared branch finishes | 776 | 26 |

Each set includes one matching shared victory. Branch results overlap selected
results and must not be added as independent games. Both recorded blocked cases
have no winner. The known defect appears in three- and four-player games, not
two-player games. A focused fixture uses setup 95,000,017, turn 107: scores
16/16/14, purchased-card counts 19/18/16, local winner mask `2`, and reference
winner mask `3`.

Evidence: `docs/results/reference-winners.jsonl.gz` and its summary. The same
five-argument boundary export command now includes winner masks. All prior
paths and snapshot fields were compared and remain unchanged after removing
the new masks. Old archives remain readable, with no retrospective winner claim.
The local engine and replay version remain unchanged. Lower-place ranks,
reference forced-pass outcomes, RNG, and hidden-information behavior remain
outside the comparison; full parity is not claimed.

## Measured boundary coverage

The harness now counts boundary events only after a shared successor passes
comparison. Selected-turn counts and sampled branch counts remain separate;
branches overlap selected turns and are not additional independent games.
All defined counters include zero values, so missing coverage is visible.

Rechecking the existing winner archive with the new counters gives:

| Shared boundary | Selected transitions | Branch transitions |
| --- | ---: | ---: |
| Tier 1 final deck draw | 36 | 42 |
| Tier 1 purchase after deck exhaustion | 122 | 72 |
| Tier 1 reservation after deck exhaustion | 2 | 37 |
| Tier 2 final draw / exhausted purchase / exhausted reservation | 0 / 0 / 0 | 0 / 0 / 0 |
| Tier 3 final draw / exhausted purchase / exhausted reservation | 0 / 0 / 0 | 0 / 0 / 0 |
| Reservation without gold available | 62 | 204 |
| Return includes gold | 8 | 285 |
| Required gold payment | 170 | 202 |
| Free purchase | 812 | 499 |
| Noble awarded after take | 1 | 0 |
| Noble awarded after visible reservation | 1 | 0 |

Optional-gold paths remain excluded as a reference difference. The gold-payment
counter therefore describes required gold only among checked shared paths.
An action requiring a final draw is distinct from one taken after the deck is
already empty. A zero in this table is a sampling gap, not a rule mismatch.

Evidence: `docs/results/reference-coverage.summary.json` rechecks the unchanged
`reference-winners.jsonl.gz` archive. It retains the raw case hash and records
the new harness hash. Existing counts remain 5,016 matched selected transitions
and 11,889 shared branch successors; this is additional classification, not new
sampled games or a larger parity claim. All 31 Python tests pass, including two
new counter tests and the 15 external-reference tests.

The next narrow coverage target is the full action sets at the two observed
non-purchase noble acquisitions. Current boundary sampling triggers explicit
noble choice, final-round entry, and termination; a single automatic noble
acquisition can occur between those samples. Tier 2/3 deck-exhaustion boundaries
also remain open and need explicit legal-history evidence or clearly labeled
constructed-state tests before a coverage claim.

## All noble-acquisition boundaries

Boundary exports now declare `noble_acquisition_choices: true` and sample every
turn that removes a noble from the available set, including an automatic award
with no separate Noble action. The verifier requires the declared sample.
Legacy exports without this flag retain their previous sampling contract; they
are not retroactively treated as complete at automatic-award boundaries.

Re-exporting the same 60 games adds 90 sampled positions and 1,852 shared branch
successors. All match the pinned reference. Totals are now 758 positions and
13,741 shared branch successors (3,750 two-player, 4,488 three-player, 5,503
four-player). Noble-acquiring branches increase from 138 to 371. This includes
45 take branches and 44 visible-reservation branches with a noble award, closing
the specific non-purchase sampling gap found in the coverage audit. Explicit
noble-choice branches increase from 16 to 22. Terminal/winner counts are unchanged.

Every selected case and every previously sampled choice set is byte-for-byte
equivalent as parsed JSON. The added samples do not change the selected policies,
seeds, transitions, or engine semantics. This is more branch coverage within the
same games, not 90 new games or independent trials.

Evidence: `docs/results/reference-all-nobles.jsonl.gz`, its comparison summary,
and `reference-all-nobles-delta.json`. The delta identifies each new sampled
position and confirms preservation of old cases. Reproduce with the same
five-argument exporter command listed above. Focused fixtures cover seed
95,000,015 turn 89 (reservation) and seed 96,000,000 turn 103 (take), and tests
reject deletion of either required sample. All 55 Rust and 33 Python tests,
formatting, and strict all-target workspace Clippy pass.

Tier 2/3 last draws and exhausted-deck actions still have zero coverage in this
workload. The other reference rule, hidden-information, and RNG differences
remain explicit; full parity is not claimed.

## Legal high-tier depletion histories

Two new cooperative coverage histories fill the tier 2/3 gap. The maintained
`depletion_history` example favors drawing down a selected tier, avoids purchases
that directly reach 15 points, and uses fixed seeded exploration. It is a test
case generator, not a competitive agent or a strength experiment. Every move is
legal, every transition passes invariants, and the full replay matches its saved
state. No state is constructed by assigning cards or changing decks.

Tier 2 uses four-player seed 107,001,000: 114 turns, 170 decisions, scores
12/10/9/4. Tier 3 uses seed 107,002,003: 115 turns, 171 decisions, scores
7/8/8/11. Both end at nonterminal replay prefixes after a final draw and both
kinds of market removal from the exhausted tier. The first three tier-3 search
attempts reached normal terminal states before covering both removal types;
those failed coverage attempts are recorded, not counted as successful cases.

The exporter's `--history FILE ZERO_BASED_TIER` mode validates the full history,
then enumerates every compound action from positions with at most one card
remaining in that tier. At the replay endpoint it selects one legal enumerated
branch as the primary comparison and retains every alternative. Metadata
`depletion_tier` declares the required sampling contract.

| Target tier | Sampled positions | Shared branches | Final-draw branches | Empty-deck purchase branches | Empty-deck reservation branches |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 | 16 | 276 | 1 | 3 | 2 |
| 3 | 25 | 313 | 2 | 2 | 4 |

All 589 shared successors match the pinned reference. Forty selected transitions
match; one tier-3 selected path is excluded for the documented return-collected-
color difference. These are two new legal-history workloads, separate from the
60-game all-noble archive. Branches remain overlapping alternatives, not
independent games. This closes the specified high-tier coverage gap, not the
remaining rules, RNG, private-information, or rank differences.

Evidence: `docs/results/reference-depletion-tier-{2,3}.jsonl.gz` and summaries;
`docs/results/depletion-history-search.json` records generator/input hashes,
failed attempts, and exact reproduction of both history fixtures. Reproduce:

```sh
cargo run --release --locked --example depletion_history -- /tmp/new-depletion-histories
cargo run --release --locked --example parity_export -- --history crates/splendor-arena/tests/fixtures/depleted-tier-2-v1.json 1 > /tmp/tier-2.jsonl
cargo run --release --locked --example parity_export -- --history crates/splendor-arena/tests/fixtures/depleted-tier-3-v1.json 2 > /tmp/tier-3.jsonl
```

Run `check_reference.py` on each export as above. A Rust regression test checks
both full histories, the last-card refill, and subsequent empty market slots.
An external-reference regression checks all branch successors and rejects
missing declared samples. All 56 release Rust tests, 34 Python tests, formatting,
and strict all-target workspace Clippy pass. Engine semantics are unchanged.

## Reservation visibility and ordered slots

An audit found a gap in the comparison harness: changing an opponent's blind
reservation to public after an unrelated take still returned `matched`. The
reference stores reservation identities but no corresponding public/private
flag, and the shared normalization intentionally removes that field. The
reproduction is seed 94,000,001, turn 11.

The harness now checks local reservation bookkeeping before reference
normalization. Uninvolved players keep the same ordered reservation list.
Visible reservations append the selected card with `public: true`; blind
reservations append one entry with `public: false`. Reserved purchases remove
the selected slot and preserve all surviving card identities, visibility flags,
and order. Other actions preserve the list. Flags must be JSON booleans.
These checks also cover exported branches excluded from external rule parity.

This is an explicit local contract check, not evidence that the reference has
matching hidden-information behavior. In particular, importing a privileged
blind-card identity for isolated transition comparison does not give it to a
production agent or establish reference observation parity.

Rechecked all three current archives with these checks. Their prior action,
transition, and outcome counts are unchanged. The main 60-game workload contains:

| Purchased reservation | Slot 0 selected / branch | Slot 1 selected / branch | Slot 2 selected / branch |
| --- | ---: | ---: | ---: |
| Public | 53 / 36 | 34 / 44 | 39 / 36 |
| Blind | 15 / 14 | 5 / 16 | 12 / 13 |

Slot numbers are zero-based. Branch and selected counts overlap. The new
`*-visibility.summary.json` files record the existing raw case hashes and new
harness hash; the raw archives are not replaced. Tests reject unrelated public
flag changes, malformed flag types, incorrect append visibility, survivor flag
changes after each slot removal, and corruption of an excluded blind branch.
All 37 Python tests pass with the pinned reference. No simulator behavior changed.


## Engine v2 regression comparison

Version 2 adds only the explicit counter-capacity resource contract described
in VALIDATION.md. Re-exported the current all-noble and two high-tier depletion
workloads under v2 and reran the pinned independent checker. All 5,511 case
lines and their branch successors are byte-identical to the prior exports,
excluding metadata. The checker still validates 14,330 shared branch successors
and 5,056 selected shared transitions, with the same explicit rule differences
and reference winner defect. This does not extend the external parity scope.

Current archives: `results/reference-v2{,-tier2,-tier3}.jsonl.gz`, with matching
`.summary.json` files. `results/capacity-validation.json` records source identity,
raw hashes, identical payload hashes, and the corresponding v1 archive names.
Older archived reference exports retain their v1 metadata. These exports are
diagnostic comparison cases, not replay histories and not evidence of counter
handling in the independent reference.

## Token accounting on excluded paths

The harness now checks local token accounting before it accepts a known rule
exclusion. For every selected nonempty turn and every exported branch successor,
it derives bank/hand transfers from the encoded take, reservation gold, discounted
payment, and excess return. It rejects overdrafts, overpayment, invalid return
amounts, changed opponent hands, and mismatched bank/hand successors. This is a
local contract check, not external transition parity for excluded actions.

Two pre-fix regressions show that an excluded selected turn or blind branch
could carry unrelated token corruption. The tests now reject both new tokens
and a wrong transfer that preserves total supply, under blind reservation,
optional gold, and collected-color return exclusions. Raw
pre-fix failures are in `results/excluded-token-before.txt`.

Rechecked all three v2 archives with the stronger harness. Their case hashes,
external match/exclusion counts, shared successor counts, boundary coverage,
and winner classifications are unchanged. New summaries are
`results/reference-v2{,-tier2,-tier3}-tokens.summary.json`; the prior summaries
remain intact. All 41 Python tests pass with the pinned reference.
