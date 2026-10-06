# Research work log — 2026-09-25

Worktree: `splendorust-astra`, branch `codex/simulator-parity`.
The work remains local. No push, release, or API-key use.

## Initial assessment

The initial commit already had 41 passing Rust tests, versioned replay fixtures,
a million-trajectory invariant audit, measured agent comparisons, and a retained
profile-driven cache change. Repeating those experiments had low value. The
largest documented gap was comparison with a licensed independent engine.
The next useful areas were malformed observation handling and preservation of
experiment evidence. No rule or agent tuning was justified by the initial
records alone.

## Completed changes

- `005b809`: Pinned MIT-licensed reference, exact 90-card / 10-noble data match,
  5,016 shared turn matches, explicit rule-difference exclusions. See PARITY.md.
- `9a8bafa`: Shared compound choices match at 574 positions (10,258 choices).
  Includes two blocked local positions where the reference offers a pass.
- `d303f1b`: Reproduced and rejected a caller-supplied opponent blind-card
  identity that did not survive observation round-trip.
- `456045f`: Reproduced an empty-input archive run deleting prior index entries.
  Archive collection now preserves prior evidence and rejects name conflicts.
- `106db4c`: Reproduced a promotion with NaN throughput. Added numeric checks,
  unused output directories, failure records, parameters, and evidence hashes.
  A real 20+20 strong/strong workflow smoke retained the baseline as expected.
- `96850a7`: Reproduced malformed final-round, market-refill, and turn-order
  metadata passing validation. Added invariant checks and targeted tests.
  Updated one fixture to use legal opponent turns instead of changing seats.

After the last core change, formatting, strict all-target workspace Clippy,
and all 47 release Rust tests passed. Re-exporting the parity workload produced
5,470 byte-identical case lines; only the source identifier changed to
`43cc5ca9d3ac763e`. Rules, enumeration, valid RNG steps, and replay semantics
remain engine version 1. The new checks reject malformed inputs.

## Current measurement

Add fixed opening/turn-40 fixtures for hidden-state sampling and invariant
checks at 2/3/4 players. Setup seed 42, trajectory RNG seed 123, sampling RNG
seed 456. Criterion uses 20 samples, one-second warm-up and measurement windows,
the pinned release bench profile, and baseline `sparse-before`.

Measured optimization: iterate owned-card set bits instead
of scanning all 90 IDs for each player in validation and hidden-state sampling.
Ascending card order and RNG steps are unchanged. All 1,000 fixed search records
matched, including one blocked game. Sampling improved about 35-43% and
invariants about 29-59% on these fixtures. Retain the change; see BENCHMARKS.md.
The incomplete run is not promotion evidence.

## Latest research and next issue

E9, the blocked-rollout penalty, was implemented as a separate candidate and
rejected by `scripts/promote.py`. Its 2,000-game screen at seed 98,000,000 had
1,943 completions, six blocked games, and 51 decision limits. Original search
self-play on the same seeds had exactly the same status for every game. Only
nine records changed. The candidate completed the known blocked development
probe but did not reduce screen failures. Confirmation seed 1,098,000,000 was
not used. Active agent code is restored; the candidate patch and reports are
archived. See EXPERIMENTS.md E9 and commit `fc85c09`.

A capped original-search replay at setup seed 3,717,527,058,913,988,934 reproduced
20,000 decisions with invariants checked, trajectory `0f0d8df6a15de62a`.
The last 100 decisions alternate take green/black and return green/black.
Both players have three reservations; one main action can leave all decisions
to the static return heuristic. Full replay: `docs/results/search-selfplay-cap-v1.json.gz`.

Next valuable issue: test an observation-only response to repeated return
positions. Write a fresh hypothesis before any agent change. Do not treat
E9's zero-value blocked leaf as a solution to legal cycles. A new candidate
must use new screen/confirmation seeds and fixed budgets. Original self-play
failure counts are not evidence of a core rule failure.

The archive validator now rejects truncated records, malformed rotations,
repeated setup blocks, inconsistent completion totals, and unfinished winners.
All 32 existing archived reports passed without modification (`f685a9b`).

## Remaining boundaries

Parity is bounded to the documented shared rules and sampled states. The
reference differs on blind reservations, payment/return choices, reduced takes,
a color-card cap, forced pass, tiebreak scoring, and hidden information. There
is no full-engine equivalence claim. No-action positions remain unresolved by
the publisher rules and have no assigned winner. Fresh confirmation seeds are
still the researcher's responsibility; new output directories do not prevent
reuse of a holdout in a different directory.

## E10 checkpoint

The repeated-return candidate completed the capped development setup in 118
turns. On fresh screen seed 99,000,000 it completed 1,990/2,000 games, with six
blocked and four capped. Original self-play on the same seeds completed 1,940,
with seven blocked and 53 capped. Paired records show 50 formerly unfinished
games became complete; no completed control game became unfinished. The gate
still rejected the candidate because ten games were incomplete. Confirmation
seed 1,099,000,000 was not used. The candidate was removed from active agents;
its source patch, targeted test, and reports are archived under E10.

A permanent version-1 replay prefix and test now demonstrate the natural
four-decision cycle: after return/take/return/take the same observation recurs
except for two additional completed turns. No outcome is assigned. All 48
release Rust tests, formatting, and strict all-target workspace Clippy pass.
The two new paired report archives pass structural validation.

Next useful reproducibility issue: reports record search configuration only as
a Rust debug string. A structured, validated run configuration would make exact
reruns less dependent on manual transcription. Keep older reports readable and
keep configuration data outside the core and agent observation boundary.
Further agent work can inspect E10's four remaining capped states, but must use
a new written hypothesis and fresh confirmation seeds before a new candidate.

## Structured report settings checkpoint

New arena reports contain all run settings as structured JSON. The agent and
core crates still have no serialization dependency. The `verify-report` command
checks engine/source identity, rejects timed or legacy settings, checks duplicate
metadata, then reruns and compares every ordered game record. It does not claim
to verify timing or statistical summaries. Incomplete records can reproduce;
this does not make them eligible for promotion. No engine version change was
needed because legal actions, RNG, and replay semantics did not change.

Validation: formatting, strict release all-target workspace Clippy, all 50
release Rust tests, and all 16 Python tests passed. Tests include non-default
search settings, all policy variants, precise durations, malformed settings,
legacy reports, changed records, and capped reruns. A CLI smoke run used 20 games,
seed 100,000,000, search/strong, two threads, seven iterations, depth three, width
two, and invariant checks. All 20 completed and all rerun records matched.
`docs/results/settings-smoke.json.gz` preserves the raw report. Its source ID is
`48500c720f030f9e`; record-set SHA256 is
`e74e17e3bdd342dcc2baa9fe0951de127f20f878f5065509658ab4dfbeba2316`.
This small smoke run is not an agent strength experiment.

Next: audit whether archive validation checks the new settings as well as the
per-game records. Then inspect the remaining E10 capped trajectories if no more
material report-integrity gap is found. Independent parity remains bounded to
the checked shared rules; the published blocked-state gap remains open.

## Archive settings validation

The archive path now checks structured settings when they are present. It
rejects conflicting seeds, agent names, limits, invariant flags, invalid search
policies/counts/durations, unknown fields, and inconsistent reproducibility
flags before any batch write. Historical reports without these settings still
pass their existing record checks. A timed report can be archived with the
correct non-reproducible flag; it cannot pass the rerun or promotion gate.

All five archive tests pass, including eleven settings corruptions and batch
write preservation. All 35 existing raw report archives pass validation. This
change affects Python evidence tooling only; it does not change engine or agent
behavior. Next investigate E10's four remaining capped trajectories, starting
from archived evidence and its saved candidate patch.

## E10 residual-cap diagnosis and E11 hypothesis

Restored E10 at its documented source in a separate temporary worktree. All four
capped screen records and trajectory hashes match. The candidate repeats the
same return observation on successive turns, changes returns, then chooses a
take again despite legal purchases. Full histories and a reproducible diagnostic
harness are archived. The main checkout's agents remain unchanged at this point.
E11's written hypothesis now tests a targeted purchase override on repeated main
observations, with separate main/return memory and fresh screen/confirmation seeds.

## E11 checkpoint

The fresh 2,000-game screen completed 1,999 games with zero caps and one blocked.
The original-search control completed 1,951, with 48 caps and the same blocked
record. All 48 formerly capped games completed; no completed game became
unfinished. The candidate's strength interval still includes equal strength.
The gate rejected the incomplete screen and did not use confirmation seed
1,101,000,000. Active agents were restored. Source patch, candidate tests, probe
histories, paired reports, and decision are archived. All 51 final release Rust
tests, formatting, and strict workspace all-target Clippy pass.

The one remaining blocked history has no repeated candidate return phase and
only one choice on its last two main decisions. Cycle memory alone cannot fix
that path. The retained core replay test demonstrates a repeated position with
affordable purchases; legal token takes must still remain available.

Next high-value evidence issue: the promotion script reads the report's supplied
confidence interval without checking its game records. Archive validation now
checks those records and settings, but the promotion decision does not use that
check. Inspect and close this boundary with a corrupted-report regression and
an independently recomputed interval before more agent experiments. Full parity
is still not claimed; reference exclusions and published-rule gaps remain.

## Record-based promotion decisions

Closed the gap between archive validation and the promotion gate. The gate now
checks records and exact requested stage settings, checks version-1 setup seeds,
and requires stable engine/source identity across stages. It derives the
candidate interval from records and rejects inconsistent supplied intervals.
Throughput is checked against elapsed time and game count. Explicit CLI search
settings prevent changed defaults from silently changing a run. The manifest
and decision now fingerprint both Python evidence tools.

All 21 Python tests pass. Two real 20+20 strong self-play workflow checks on fresh
seeds retained the baseline with 50% credit. The checks also ran formatting,
strict workspace Clippy, and all 51 release Rust tests. Raw evidence, manifests,
and decisions are archived under `docs/results/record-gate-*`. No Rust source,
agent policy, rule, RNG, or replay semantics changed.

Next: return to independent parity coverage. The existing external comparison
samples full shared action sets every ten turns but tests data/adapters through
a few mutation regressions. Audit whether player-count, tie, terminal, and
noble-choice boundaries are directly exercised by checked reference cases;
add targeted reproducible coverage for a material missing boundary rather than
merely increasing random sample counts. Keep reference rule differences explicit.

## Independent comparison path validation

Audited the archived boundary coverage before adding cases. Existing inputs
already include multiple nobles, depleted decks, market gaps, and final rounds.
Found and reproduced a harness error: changing an explicit noble-choice ID from
7 to 8 still matched because the adapter trusted the successor's noble. Fixed
encoded-path checks, including required noble phases, duplicate phases, byte
shape, and padding. The targeted optional-reference regression passes.

Rechecked the existing archived workload under the repaired harness: 5,016
shared transitions and 10,258 shared choices at 574 positions still pass, with
unchanged explicit exclusions. This is stronger verification of old evidence,
not new sampled coverage. The summary and small noble-choice fixture are saved.
No Rust or simulator semantics changed.

Next gap: complete action sets currently check each alternative's signature,
but only the selected turn has its resulting state compared with the reference.
Extend the diagnostic export to include successor snapshots for sampled choice
branches, and verify those snapshots with the same external transition check.

## Independent branch successor comparison

Extended the offline exporter with optional format-2 branch snapshots. The
reference harness now verifies every shared sampled choice's successor, not
only the selected policy path. Missing branch snapshots and corrupt branch
scores are rejected. Old format-1 archives remain readable.

The fixed 60-game workload checks 10,258 shared branch successors at 574 positions
(2,650 two-player, 3,167 three-player, 4,441 four-player). It covers 57 terminal
successors, 50 noble acquisitions, and four explicit noble-choice branches.
Selected transitions and exclusion counts remain unchanged. Compared all old
and new exported cases after removing the new snapshots: every selected action
path and choice signature matches. The compressed format-2 evidence and summary
are archived. Formatting, strict release all-target workspace Clippy, and all
51 release Rust tests passed. The optional reference tests include new branch
mutation checks. No engine version change is needed for this diagnostic format.

Next parity boundary: explicit multiple-noble branch successors in this regular
sample occur only at two-player positions. Existing three-/four-player selected
paths contain such phases outside the every-tenth-turn sample. Add targeted
sampling of observed noble-choice and terminal boundaries, then verify full
branch successors there. This can extend rare-case coverage without merely
increasing random game counts. Outcome tiebreak differences remain explicit.

## Multiplayer boundary parity

Added optional choice sampling at observed noble-choice turns, terminal turns,
and starts of the final round. The same 60-game workload now checks 11,889 shared
branch successors at 668 positions. It includes six explicit three-player noble
branches and four four-player branches, plus six two-player branches. It checks
802 terminal successors and 138 noble acquisitions. All old paths and sampled
branches remain unchanged. New cases and exact counters are archived.

The boundary sample also exercises one known seven-card reference restriction;
a focused fixture now checks that exclusion. The harness rejects missing whole
samples required by the declared interval or boundary mode. All 26 Python tests,
51 release Rust tests, formatting, and strict release all-target workspace
Clippy passed. No engine or policy semantics changed.

Next: compare normal-game winner masks explicitly. The reference's documented
fewest-card defect is observable in existing data: setup 95,000,017 at turn 107
has leaders at 16/16 points with 19/18 cards, while a nonleader has fewer cards.
Add actual engine winner masks to the diagnostic export and distinguish checked
matches from this precise reference defect. Do not compare lower-place ranks
against the reference's different score-adjustment convention or award winners
to blocked cases.

## Normal-game winner comparison

Added actual engine winner masks to diagnostic snapshots and required them when
the export declares winner checking. Local masks are checked against tied-leader
fewest-card rules. The harness also checks the exported complete-turn final-round
and terminal flags, keeps nonterminal masks null, and compares reference
`calScore` winners after shared normal transitions.

The boundary workload has 50 selected winner matches and two instances of the
known reference defect; its shared branches have 776 matches and 26 instances.
Both result groups include one shared-victory match and overlap each other.
The two blocked records have no winner. The exact reference defect is classified;
other mismatches fail. A fixture shows scores 16/16/14 and owned counts 19/18/16,
where the local winner is seat one but the reference also retains seat zero.
Tests reject copying the reference's wrong mask, unexpected reference winners,
false unfinished winners, missing masks, and inconsistent round flags.

All old paths and snapshot fields are unchanged after removing the added masks.
The new compressed export and fingerprinted summary are archived. No core rule,
agent, RNG, ID, or replay semantics changed. Remaining parity limits include
lower-place rank conventions, forced-pass outcomes, hidden information, and RNG.

Validation for this checkpoint: all 29 Python tests, 51 release Rust tests,
formatting, and strict release all-target workspace Clippy pass. Next inspect
core observation validation for the reverse final-round implication: a completed
turn with threshold prestige must not lose the final-round flag. A pending noble
choice can legitimately delay that flag, so preserve valid intermediate phases
and prove any new rejection with targeted evidence before changing validation.

## Round-state observation validation

Reproduced two accepted malformed observations before changing validation. The
first relabeled a legal pending-noble state with 16 points as Main while keeping
the final-round flag false. The second relabeled the terminal seed-42 state as
Main. Both now fail with explicit invariant errors. A real four-player replay
reaches the legitimate threshold/pending-noble boundary after 228 decisions;
it still determinizes correctly for all viewers, and all noble branches finish
with the correct final-round flag. No valid transition behavior changed.

Validation: all 53 release Rust tests, all 29 Python tests, formatting, and
strict release all-target workspace Clippy pass. Re-exported the full boundary
workload under source `6fb7813c76f86a6a`: all 5,470 case lines and their branch
snapshots are byte-identical to the previous export. A fresh random invariant
audit used seed 104,000,000, four threads, and a requested 100,000 games; seat
rounding gave 99,997 games, with 89,101 completed and 10,896 blocked. No capped
outcome was assigned. Raw output and a fingerprinted comparison record are saved.
The engine stays at version 1 because valid rules, RNG, enumeration, and replay
semantics are unchanged.

Next high-value agent investigation: E11's sole blocked screen history has a
first-time return choice immediately before the opponent takes the last colored
token. Enumerate those return alternatives and the following legal opponent
turns to learn whether a different return preserves a purchase. Do not assume
that it does, and do not change an agent before recording a supported hypothesis.
The E11 candidate remains rejected and removed from active code.

## E11 return alternatives checked

At clean baseline `9af0879`, enumerated all five candidate returns at decision
37 and all four complete opponent replies per return. All five returns allow
an immediate block when the opponent takes the returned token. Each also
permits three opponent purchases that preserve a candidate purchase. This
rejects the proposed return-only explanation for this failure; no agent change
was made. Full paths, legal actions, and hashes are archived in
`docs/results/e11-return-audit.json`, with a maintained offline Rust example.
The production source fingerprint remains `6fb7813c76f86a6a`. Formatting,
strict release all-target workspace Clippy, and all 53 release Rust tests pass.

Next: inspect the five Main alternatives at decision 32 and the opponent's
preceding purchase decisions. Determine whether a public-information feature
can predict blocking risk before the forced takes. Do not infer probabilities
from unweighted branch counts or treat this probe as fresh evaluation evidence.

## E11 earlier blocking risk located

Continued from `69741ef`. A bounded adversarial audit of decision 32 finds that
the recorded white/red/black take and the two-white take allow the opponent to
force a candidate block within seven decisions. Three alternatives do not.
The result persists at ten decisions (1,058,779 visited states); white/blue/black
has no actor-blocked leaf within either horizon. Counts are unweighted paths,
not probabilities. Actual hidden deck state is used only in this offline audit.
No agent behavior, engine semantics, or production source fingerprint changed.

Saved full history fixture, diagnostic example, fingerprinted seven/ten-decision
results, and two regression tests. Formatting, strict release all-target
workspace Clippy, 53 release workspace tests, and two example tests pass.

Next useful research task: determine which public card deficits and token-supply
features distinguish these five takes. Before any agent change, record a
hypothesis based on that observation-only calculation. E9 already tried a zero
reward for blocked rollout leaves and failed; do not simply repeat that change.
Keep E10/E11 rejected and their confirmation seeds unused. Full external parity
remains bounded by the documented reference differences in docs/PARITY.md.

## E12 affordable-purchase filter rejected

Continued from `fa34531`. Observation-only features show that the three takes
without forced blocks in the bounded E11 tree all make market card 18 affordable.
The other two do not. Recorded the E12 hypothesis at `6654cbf` before changing
agents. Tested a narrow root filter for full reservation slots, only-take legal
actions, and at most ten colored bank tokens. It keeps takes that afford a
visible/own reserved card without requiring a return, if any exist.

The known game completed, but fresh seed 105,000,000 screen evidence is mixed:
1,968/2,000 complete, 29 caps, three blocks; paired control 1,966 complete,
31 caps, three blocks. Five caps improved and three new caps appeared. Gate
rejected; confirmation 1,105,000,000 unused. Candidate removed; patch and all
raw evidence archived. Formatting, strict all-target Clippy, and all 53 release
workspace tests pass on candidate and restored baseline.

Next: inspect the three newly capped paired E12 games before combining or
changing cycle handling. Their identities are directly recoverable from the
archived E12 reports. Alternatively audit validation coverage across maintained
examples: `cargo test --workspace` does not run their tests by default, so the
block-audit regression tests currently require a separate documented command.
Do not repeat E9's blocked-leaf reward change or claim general safety from this
single public-feature case. External parity remains scoped as documented.

## Routine validation now includes diagnostic and reference tests

At `676432f`, verified that the standard workspace test command omitted both
block-audit tests and CI left all 15 independent-reference tests skipped.
Added an explicit Cargo example target with testing enabled. Updated CI to
fetch the exact pinned reference commit into the runner temporary directory
and provide it to Python test discovery; reference identity/license checks
remain enforced by the existing comparison loader.

Validation: formatting, strict release all-target workspace Clippy, all 55
release workspace tests, and all 29 Python tests passed. The reference test
used a fresh shallow fetch, not the previous cached checkout. No tests skipped.
The CI configuration is updated but hosted runs are not claimed: no push was
made. Cargo manifest fingerprint changes are expected; engine rules, replay
semantics, and active agents are unchanged.

Next unresolved research item remains the three E12 games that became capped
when their control games completed. Reconstruct their exact histories from the
archived candidate patch and compare recurrence patterns before proposing any
combined intervention. The full parity boundary remains explicit.

## E12 new caps reproduced and classified

Continued from `b7ab94b`. Restored E12 in a temporary historical worktree and
reproduced all three new capped records exactly, including trajectory hashes.
All have four-decision take/return cycles starting at decisions 87, 75, and 91.
Both sides have legal purchases throughout. E12's only-takes condition is false
in these positions, so its filter cannot change these recurrent decisions.

Archived all full histories, source/input hashes, recurrence summaries, and
reproduction harness. The first diagnostic assumption (two repeated actions
imply a state cycle) failed its observation assertion; the final detector checks
both viewers and correctly includes the active-player change. No core, rule,
or active-agent change was made. Historical candidate formatting, strict
all-target Clippy, and 53 release tests pass; the current standard suite has 55.

Next useful experiment could combine the independently diagnosed early token
scarcity and later repeated-Main failures, but only after a new written
hypothesis, with new screen/confirmation seeds. E11 already tested recurrence
handling alone and E12 affordability alone; do not present a combination as an
established improvement. An alternative useful next task is to inspect E12's
three unchanged blocked games for public features missed by the narrow trigger.

## E13 combination screen rejected

Continued from `d10ac5a`. Recorded hypothesis at `bb68482`, then combined the
exact E12 root filter with E11 recurrence handling. Initial patch integration
failed candidate registration; tests caught it before games ran and the failed
gate record is retained. Corrected candidate passed legality, repeatability,
hidden-information, and focused recurrence tests.

Four known failure probes completed. Fresh 106,000,000 screen: 1,994 complete,
zero caps, six blocks; original-search control: 1,948 complete, 48 caps, four
blocks. All control caps and one block became complete, but three completed
control games became blocked. Win interval [47.04%, 55.91%] proves no strength
gain. Gate rejects; confirmation 1,106,000,000 unused. Full reports, paired
statuses, probe histories, source patch, and failure records archived.

Candidate removed and release binary restored. Candidate's 57 and baseline's
55 release workspace tests pass, as do formatting and strict all-target Clippy.
No core or rule changes. Next valuable task: reproduce the three newly blocked
E13 games and identify whether the block affects the candidate or opponent and
whether it follows an escape purchase or a scarcity-filter decision. Compare
that evidence before changing either component. Do not assume the components'
individual effects can be inferred from this combined screen alone.

## E13 new blocks traced to the scarcity filter

Continued from `3c5a5ea`. Restored the exact E13 source in a temporary worktree.
All three newly blocked records and all three completed controls reproduce
exactly with invariant checks. In blocks 223, 237, and 855 the candidate is the
blocked player. First action divergence is the sole scarcity-filter event
(decisions 34, 29, 41). No repeated-position condition occurs in any trajectory.
The candidate buys the newly affordable market card in all three cases and
blocks later. This rules out immediate card theft and cycle escape as the
observed mechanism; local affordability is insufficient for sustained progress.

Saved all six histories, public-token features, event/purchase traces, source
hashes, and a reproduction harness. Candidate formatting, strict all-target
Clippy, and 55 release workspace tests pass. No active-agent or core change.

Next: prefer a broader evidence review before another local heuristic change.
The E12/E13 filter premise now has three direct counterexamples even though its
original probe succeeded. A useful alternative is to audit existing parity
sampling for reachable phase/data coverage and select an uncovered boundary,
or measure search rollout behavior in these blocked cases without retuning to
them. Keep the published no-action gap explicit and do not restore rejected
candidates as defaults.

## Parity boundary coverage measured

Continued from `048984c`. Reviewed the independent comparison workload instead
of tuning another local agent heuristic. Added explicit post-comparison boundary
counters, preserving zero values and separating selected transitions from
sampled branch successors. Two focused tests cover tier boundaries and gold/free
purchase classification. All 31 Python tests pass with the pinned reference.

Rechecked the unchanged winner archive: all prior comparison counts still pass.
Tier 1 final draws and exhausted-deck actions are covered, but all corresponding
tier 2/3 counts are zero. Two shared selected transitions award nobles after a
take or visible reservation (one each), but neither has sampled branch coverage.
Saved the fingerprinted coverage summary and documented these precise gaps.
No Rust, engine, replay, or agent changes were made.

Next: extend explicit boundary sampling to every noble acquisition, including a
single automatic award, with a versioned metadata flag so old archives remain
honestly interpreted. Re-export the same workload to target these known omitted
action sets; compare only genuinely new branches as added coverage. Then consider
legal-history generation for tier 2/3 exhaustion. Do not count the coverage
reclassification as new independent games or claim full parity.

## Automatic noble boundaries now have full branch comparison

Continued from `ce0773d`. Extended boundary sampling to all noble acquisitions,
including automatic single awards. New metadata flag
`noble_acquisition_choices` makes the stronger contract explicit; the verifier
requires those samples and preserves legacy behavior without the flag.

The same 60-game workload adds 90 positions and 1,852 matched shared branch
successors: now 758 positions and 13,741 branches. Non-purchase noble branches
are now covered (45 takes, 44 visible reservations); explicit noble branches
increase to 22. Selected cases and all previous choices remain unchanged,
verified by a delta comparison. No new independent games are claimed.

Saved the full archive, fingerprinted summary, delta, and two automatic-noble
fixtures. Tests reject missing declared samples. All 55 release Rust tests,
33 Python tests, formatting, and strict all-target workspace Clippy pass.
No ENGINE_VERSION bump: only diagnostic sampling changed.

Next parity gap: tier 2/3 final draws and exhausted-deck actions still have zero
shared coverage. Seek legal histories that intentionally draw down those tiers
without triggering early terminal play, or explicitly label any constructed
states and validate their invariants. Do not imply that tier-1 exhaustion tests
prove all tier boundary behavior.

## High-tier exhaustion parity gap filled with legal histories

Continued from `791b6c7`. Added a fixed-seed cooperative coverage generator.
Initial short prefixes reached depletion but did not expose both exhausted
market removal types, so extended the stop condition to cover purchase and
reservation. Tier 2 succeeded at seed 107001000; tier 3 at 107002003 after three
attempts ended normally before satisfying both coverage requirements. Failed
attempts and exact fixture reproduction are recorded.

Added history-boundary mode to the exporter and explicit required sampling
metadata. No state assignment, hidden deck editing, core changes, or agent
changes. Full legal histories now have last-card refill and empty-slot regression
coverage. Shared parity: 276 tier-2 branches at 16 positions and 313 tier-3
branches at 25 positions. All match. One selected tier-3 path has the existing
return-collected-color exclusion. Archives and source/input hashes are saved.

Final validation: 56 release workspace tests, 34 Python tests with the pinned
reference, formatting, and strict all-target Clippy pass. No engine bump needed.
Next evidence review: test depletion behavior across player counts (these new
histories are four-player only), or inspect coverage of buying public versus
blind reserved cards and their slot compaction. Preserve explicit differences
rather than claiming these additions establish full parity.

## Reservation metadata verifier gap fixed

Continued from `2188271`. Reproduced an accepted corrupt export: a blind opponent
reservation changed to public after a take at seed 94000001 turn 11, but the
reference comparison still matched because its normalized representation drops
visibility. Added explicit local reservation bookkeeping checks before external
normalization, including excluded branch successors. Kept the distinction from
external observation parity explicit.

Checked public/blind appends, exact ordered removal on purchases, untouched
opponents, and boolean flag types. Added three tests including the real corrupt
case and an excluded blind branch. New coverage counters show checked purchases
from all three public and blind slots. Revalidated all-noble and both depletion
archives with unchanged shared transition/outcome counts. All 37 Python tests
pass; no Rust or active-agent changes. New summaries preserve old raw archives.

Next useful robustness review: the parity export's hidden metadata is now
checked locally, but published reference limitations remain. Inspect arena
serialization/report validation or core malformed-observation rejection for
uncovered numeric/phase boundary failures; do not spend another pass merely
recounting already covered reservation slots. Cross-player-count depletion is
also still an explicit extension opportunity, not a proven gap in engine rules.

## Reject impossible final-round seat order

Continued from `f3e0d24`. Audited malformed-observation validation and reproduced
accepted impossible final-round states before editing the core. Added checks
requiring an earlier finished threshold turn for nonterminal final_round=true,
and rejecting threshold scores in unplayed seats (except the current actor's
valid pending Noble phase). Preserved valid pending and completed noble turns.
Two focused replay tests use existing real threshold/tiebreak trajectories.

All 58 release Rust tests, 37 Python tests, formatting, and strict all-target
Clippy pass. Fresh 108,000,000 audit: 99,997 games, 89,068 complete, 10,929 blocked,
no invariant failure. Re-exported all three parity workloads: 5,511 case lines
and all their branches byte-identical except metadata. Source fingerprint is
`3992ef689453dcc8`; old archives remain intact and comparison hashes are saved.
No ENGINE_VERSION bump because legal transition/RNG/enumeration/replay behavior
is unchanged; only impossible input validation is stricter.

Next useful robustness audit: inspect long-running legal cycles at integer turn
counter boundaries and arena decision-limit parsing. Distinguish malformed
inputs from genuinely reachable very long games before choosing a fix; any
change to valid replay semantics requires explicit versioning. Do not repeat
completed reservation/noble/depletion comparisons without a new failure or gap.

## Search depth overflow

Continued from `f200420`. Reproduced a search depth arithmetic defect with a
legal turn-one observation and depth `u32::MAX`: debug panics, release wraps and
changes the selected action. Replaced the absolute deadline with elapsed turns.
No engine transition, replay, or enumeration change; ENGINE_VERSION stays v1.

All 59 release workspace Rust tests and 37 Python tests with the pinned reference
pass, as do formatting and strict release all-target Clippy. The 100-game fixed
seed 109,000,000 comparison preserves every record. Archived both full reports,
source/record hashes, and pre-fix debug/release failures. No strength or runtime
improvement claim. Core turn-counter exhaustion remains explicit and unfixed.

Next: inspect the public arena `play_game` entry point, which bypasses config
validation and adds a caller-supplied rotation before modulo. Test invalid
player counts and extreme rotations before changing its error contract.

## Direct arena input validation

Continued from `a45f01f`. Three pre-fix tests show the public `play_game` API
accepts invalid run settings and panics on 258 agent names or `usize::MAX`
rotation. Logs are in `docs/results/direct-game-before.txt`. CLI and tournament
callers already validate settings, so this defect concerns direct library use.

The public API now validates the same RunConfig contract as tournaments and
rejects noncanonical rotations before seat arithmetic. The internal tournament
runner retains one validation per run. A regression compares public direct
calls with tournament records at every seat for 2/3/4 players; capped games
still have zero winners/ranks and their histories replay. No engine rules,
enumeration, RNG, or replay changes; ENGINE_VERSION remains v1.

Validation: all 63 release workspace Rust tests and 37 Python tests against the
pinned reference pass. Formatting and strict release all-target Clippy pass;
the four direct-call tests also pass in debug. Next open issue: establish a
reproducible test at the core's turn-counter boundary before deciding whether
to widen the counter or return an explicit resource-limit error. This is not
a published-rule terminal outcome and must not assign winners.

## Reachable turn-counter boundary audit

Continued from `fe685a0`. Added `turn_limit_audit`, which verifies the existing
legal token cycle, skips only a whole number of identical two-turn repetitions,
and determinizes the resulting observation at turn `u32::MAX`. This is a
reachable public state argument, not a fabricated initial-board counter or
an assertion that billions of turns were replayed. It preserves only the
observation, not the original hidden deck; the cycle never reads that deck.

Both profiles reproduce the next Return defect: debug mutates tokens then
panics and fails the Return invariant; release wraps to zero and passes
invariants. Neither has an outcome. Archived JSON and stderr identify source
`ae728260bd1abd30`. This audit changes no engine behavior.

Next: implement an explicit, atomic core resource-limit error at the existing
counter capacity and handle it in search. Bump ENGINE_VERSION and version
current golden fixtures because valid unbounded cycle execution changes at
that limit. Keep old evidence and fixtures available for their original engine
version. Do not silently saturate, wrap, invent a terminal state, or treat
resource exhaustion as a published-rule stalemate.

Validation: formatting, strict release all-target workspace Clippy, and all
63 release workspace Rust tests pass. Both diagnostic runs completed and their
counter failure evidence was inspected. The audit is intentionally not a test
that requires buggy behavior to continue; a future fixed engine can emit a
resource error in the same diagnostic.

## Engine v2 atomic counter capacity

Continued from `e03b638`. Fixed the confirmed reachable counter defect with
`RuleError::TurnLimit`, checked after legality but before any mutation. All
phases use the same guard. Legal enumeration stays intact; capacity does not
create a terminal state or winners. A real final turn can reach the maximum
and still produce its normal outcome. Search stops rollouts at capacity and
uses its existing nonterminal evaluator, with a heuristic fallback at a root
already at capacity. Arena errors propagate rather than creating a report.

Bumped ENGINE_VERSION to `splendorust-v2`. Retained all ten old golden fixture
files unchanged, added v2 copies, and verified only their engine labels differ.
The current replay tests, diagnostic examples, and reference tests use v2.
Old engine histories are explicitly rejected. Updated the promotion stage
validator and its version-rejection test. JSON history format remains 1.

Validation: formatting, strict release all-target workspace Clippy, all 68
release Rust tests, and all 37 Python tests against the pinned reference pass.
Debug/release audits both return TurnLimit with unchanged state and valid
invariants. Added tests for atomic rejection across all decision phases,
near-capacity search, and a real terminal turn reaching the limit.

The 1,000-game search/strong comparison at seed 110,000,000, 64 iterations,
depth 8, width 6 has identical records before/after, all complete. Sources:
v1 `ae728260bd1abd30`, v2 `93aa7293171a9875`. Archived reports and record hashes.
Re-exported and checked all three current reference workloads under v2:
5,511 case lines byte-identical except metadata, 5,056 matched selected
transitions, and 14,330 checked shared successors. Known reference differences
and winner defects remain explicit. No full parity or strength claim.

Next useful audit: inspect replay/report tooling for version assumptions after
this intentional engine change. In particular, confirm archived historical
reports remain inspectable without being eligible for new promotion or silent
replay relabelling. Then return to any uncovered public-rule/action boundary;
do not repeat the same three parity exports without a new change or gap.

## Report version boundaries

Continued from `7d3f7f7`. The full promotion workflow already rejected old
engine reports, but the separately callable `decision` helper could still
return promote for a synthetic old-engine report. Added a shared v2 engine and
nonempty source check to both entry points. Archive index entries omitted both
identities; added engine and nullable source fields without rejecting older
reports or inventing missing fingerprints. Two pre-fix failures are preserved.

All 49 archived reports remain readable and preserve engine/source metadata:
48 v1, one v2, with 17 missing historical source fingerprints. The audit records
raw and tool hashes. All old-engine decisions reject. Current CLI verify-report
rejects the v1 capacity report and reproduces every one of the 1,000 v2 records.
All 39 Python tests pass against the pinned reference. No Rust, core semantics,
or agent changes, so the production fingerprint remains `93aa7293171a9875`.

Next: return to rule coverage. Inspect the local tests for each known external
reference exclusion, especially optional gold and return of collected colors,
and identify any missing boundary rather than repeating matched parity cases.

## Local coverage of reference exclusions

Continued from `be25091`. Audited known exclusions against Rust tests. Payment
and return generators already have independent Cartesian checks, and return
branches already check full invariants. The optional-gold purchase test used a
manually replaced market card, so it could not verify complete card partition
or conserved bank supply. Added a consistent-state test of all 16 payment
subsets, including all gold, for both market and reserved sources. All 32
branches check exact bank/hand payment, ownership, bonus, reservation removal,
turn advancement, and invariants.

Also added a valid-state purchase from seven to eight cards of one bonus color.
The existing Python fixture classifies the reference's seven-card cap, but this
new Rust test directly checks the local engine and full state conservation.
These are local validation additions, not new external parity claims.

All 70 release workspace Rust tests and 39 Python tests pass, as do formatting
and strict release all-target Clippy. No runtime source changed; the build's
source fingerprint nevertheless changes to `5fbacedf05ec987b` because it hashes
core test source as well. ENGINE_VERSION remains v2.

Next useful work: measure current core transition costs against pre-capacity
v1 with a fixed release workload. Recent correctness checks have not yet had a
controlled runtime comparison; do not infer a cost or optimize without one.

## Counter-check performance measurement

Continued from `388243b`. Built a detached v1 `e03b638` worktree and current v2
with identical benchmark source, toolchain, lockfile, and bench profile. Both
builds completed before six serial Criterion runs in ABBAAB order. Forty
samples per operation, one-second warm-up/measurement, same opening action and
seed-42/RNG-123 random game. Recorded source identities, host/compiler, exact
commands, raw log hashes, and all Criterion estimates in capacity-benchmarks.json.

Median-of-means changes: batched apply +0.6%, clone/apply +0.9%, fixed random
game -1.4%. Small mixed local results do not justify an optimization. No runtime
change was made, and no broad speed claim is supported. The pre-existing
1,000-game identical-record evidence is referenced separately, not presented
as the benchmark's workload. Removed the clean temporary baseline worktree
after preserving measurements. Current worktree remains the isolated branch.

Next: audit benchmark coverage before another timing study. The current apply
benchmarks cover only an opening Take; payment/return/noble transition costs
have no isolated fixed-state measurements. Add phase coverage only if it can
use invariant-valid fixtures and keep setup/clone costs explicit.

## Phase transition benchmark coverage

Continued from `23df2be`. Existing apply measurements exercised only opening
Take. Added batched Main, Payment, Return, and Noble transitions with invariant
checks on both fixture and selected successor outside timing. Reused the
existing fixed trajectory for the first three phases. Offline random search
found a valid Noble at four-player seed 9 / policy RNG 123 / decision 215;
the benchmark replays that fixed prefix, without a search in measured code.
Removed the temporary search example after identifying the fixture.

Each benchmark logs action and full-state/successor fingerprint. Release
40-sample means: Main 25.33ns, Payment 26.68ns, Return 26.48ns, Noble 22.83ns.
Archived intervals, raw logs, host/compiler details, benchmark hash, and source
identity. These are baseline fixture costs, not optimization evidence or all-
phase distributions. Setup cloning is untimed; result consumption remains timed.

Formatting, strict release all-target Clippy, and all 70 release Rust tests
pass. The benchmark ran all four validated fixtures. No production code, agent,
engine version, or external parity scope changed; source remains 5fbacedf05ec987b.

Next: return to independent rule validation. Review the comparison harness's
known-difference classification order for cases with multiple differences;
ensure an excluded branch cannot hide unrelated corruption in shared fields.

## Excluded-path token validation

Continued from `6ff8cda`. The reference checker returned early for known rule
differences after reservation validation, so unrelated token errors could be
hidden by a correct exclusion label. Reproduced accepted bank corruption for
selected excluded turns and exported blind-reservation branches before editing.

Added local accounting of encoded takes, reservation gold, discounted colored/
gold payments, and excess returns. Check before exclusion in selected cases
and all branch successors. Reject overdrafts, overpayment, invalid excess,
and incorrect bank or any player's hand. Tests include both supply inflation
and conserved-but-wrong transfers for three excluded transition categories.
This does not convert excluded actions into externally matched transitions.

All 41 Python tests pass against the pinned reference. Rechecked all three
current v2 archives; raw hashes, external classifications, shared successors,
coverage, and winner counts match the prior summaries exactly. Saved new
*-tokens.summary.json results and retained the pre-fix failures. No Rust,
agent, or engine change; no new full-parity claim.

Next: inspect card/deck bookkeeping on excluded blind-reservation paths. The
existing reservation check preserves order and visibility but permits the
newly appended card identity without independently checking its tier/deck
membership. Use a concrete corruption case before adding another local check.


An added test initially treated the seven-card fixture's selected turn as
excluded. It is actually a shared turn; only one of its old-format choices is
excluded, and that choice has no successor snapshot. Removed that unsupported
test assumption. Token corruption coverage is explicitly three exclusion
categories, not four; the new accounting call also applies to seven-card
successors when they are exported.

## Blind-reservation card accounting

Continued from `6b9f2b4`. Reproduced accepted wrong-tier card corruption on an
excluded blind-reservation turn. Existing checks covered append visibility,
reservation order, and token transfers but not the new card's source tier or
partition. Added local checks for requested tier, unique IDs, per-tier partition
counts, one deck decrement, unchanged market, and unchanged ownership/bonuses.
Both selected turns and branch successors invoke the check before exclusion.

Regression cases reject wrong tier, stolen market identity, stale deck count,
market removal, changed bonus, and invalid requested tier. A same-tier unseen
alternative remains accepted by the local contract, explicitly demonstrating
that hidden top-card/RNG parity is not claimed. Preserved the pre-fix failure.

All 42 Python tests pass with the pinned external implementation. All three
current workloads pass again with exactly the same external counts, coverage,
winner classifications, and input hashes. New *-blind-cards.summary.json files
preserve this stronger local validation without overwriting earlier evidence.
No Rust or runtime behavior changed; source remains 5fbacedf05ec987b.

Next: audit complete-turn metadata on excluded paths. The checker compares
current/terminal through the reference only on shared actions. Establish whether
an excluded turn can carry an unchanged turn counter, wrong next player, or
incorrect final-round transition while still receiving a valid exclusion label.

## Excluded complete-turn metadata

Continued from `6a86036`. Reproduced an excluded blind-reservation turn retaining
its old turn counter. Added common snapshot/transition metadata validation
before exclusion on selected turns and exported branch successors. Check u32
range, strict flag types, player count, seat/counter consistency, one turn and
seat increment, no action after terminal, and final-round activation. Threshold
and terminal flag checks no longer depend on winner_mask being present, while
old exports can still omit the mask itself.

The regression covers counter/seat errors and final/terminal flag errors with
and without winner metadata; it also corrupts an excluded branch successor.
Preserved the pre-fix failure. All 43 Python tests pass with the pinned reference.
All three full v2 workloads pass with unchanged input hashes, external counts,
coverage, and winner classifications. Saved new *-turns.summary.json evidence.
No Rust or simulator semantics changed, and no external parity expansion claimed.

Next: inspect derived score/bonus and noble accounting on excluded paths. A
correct exclusion should not permit unrelated prestige or noble ownership
changes. Reproduce a specific accepted corruption before extending local checks.

## Excluded-path prestige and noble accounting

Continued from `4fc278e`. Reproduced an excluded blind-reservation turn with an
invented point. Added derived score/bonus checks, noble partition checks,
purchase ownership transitions, and mandatory one-noble acquisition from the
eligible available pool. Explicit Noble choice is required exactly when more
than one qualifies. Branch noble metadata is checked before exclusion, rather
than only for shared reference actions.

Tests reject actor/opponent prestige changes and ineligible three-point noble
awards on selected excluded paths and prestige changes in an excluded branch.
A real noble-choice fixture checks omission of a mandatory visit and an explicit
choice. Two existing score-corruption assertions initially failed because the
new local check catches corruption earlier; updated their exact diagnostics.
All 45 Python tests now pass with the pinned reference. Preserved the pre-fix
failure and three new *-prestige.summary.json reports, whose input hashes and
external counts exactly match the preceding workloads. No Rust or runtime change.

Next: broaden independent comparison evidence beyond repeatedly reused seeds.
The existing workloads are strong regression fixtures, but new confirmation
seeds across 2/3/4 players can test whether the accumulated checks generalize.
Use a separately labelled fixed workload, preserve all exclusions and blocked
states, and do not combine overlapping branches as independent games.

## Fresh independent confirmation

Continued from `473494c`. Ran the existing exporter/checker unchanged on fresh
master seed 111,000,000, 20 games per player count, interval 10, full branch
successors and all noble/final-round boundaries. Verified no overlap with the
original 60 development setups. Archived all raw cases plus per-game manifests,
source/reference identities, hashes, and exact reproduction commands.

Results: 60 games, 57 complete, three blocked (one 3p, two 4p), zero capped.
5,370 case records; 4,949 matched selected turns. At 752 sampled positions,
14,342 shared successors match. All expected exclusion categories remain
explicit, including one selected seven-card purchase and eight sampled seven-
card branches. Terminal branches: 816 winner matches and 29 known reference
four-player tiebreak defects. No unclassified mismatch, and no invented blocked
winner. No full parity claim and no pooling branch counts as independent games.

After the untouched confirmation passed, extracted a full seven-card successor
from seed 115,000,017 turn 142 and extended token-corruption tests to it. This
closes the test-data limit recorded earlier, where the old fixture's excluded
choice lacked a successor. All 45 Python tests pass. No runtime code change.
These confirmation seeds are now used development evidence for later edits.

Next: inspect the eight seven-card branch successors in this new archive and
retain a complete action-set regression if it adds coverage beyond the old
no-successor fixture. Keep selected-turn and full-action-set evidence distinct.

## Seven-card branch successor regression

Continued from `d16d3be`. Inspected all eight seven-card excluded branch positions
in the fresh archive. The old fixture has no branch successor; the new selected-
turn fixture does not exercise complete choice-set comparison. Added a compact
manifest selecting the smallest complete action set per player count from the
existing archive, with raw archive and canonical full-case SHA-256 checks.

Cases: 2p 113000013/turn79, 3p 114000015/turn103, 4p 115000005/turn140. Their
142 total paths include 34 shared successors and three seven-card exclusions.
The test retains all choices, checks exact classifications, and injects token
and noble-metadata errors into each excluded branch. Both must fail. All 46
Python tests pass against the pinned reference. No engine/runtime change and
no new independent-game count; this is coverage extracted from used seeds.

Next: review current search runtime with a new profile before proposing an agent
or performance change. The prior profile predates the sparse-owned scan and v2
validation work. Use a fixed workload, record source/settings and sampling cost,
and do not interpret a profiled run's elapsed time as clean throughput evidence.

## Current search profile and E14 hypothesis

Continued from `015453d`. Built current release, launched a fixed 10,000-game
search/strong workload (112m, 128/8/6, four threads), and sampled the live process
for five seconds at 1ms intervals. Sampling succeeded; arena completed with
9,998 normal completions and two blocked games, exiting 1 as designed. Preserved
full report, raw sample, process status, settings, hashes, and collapsed summary.
Validated report records/settings. No throughput or promotion claim uses its
profiled elapsed time.

`potential` remains the largest sampled application symbol (8,622 collapsed
samples; next action_score_cached has 813). Source inspection identifies one
specific redundant calculation: the strong Take scorer ignores base_potential,
while ReserveVisible already consumes it. Blame shows the Take expression was
in the original baseline, not introduced by recent correctness work.

Recorded E14 hypothesis before editing agents: reuse supplied base potential
with the existing fallback, prove exact score/action equality, and measure
alternating clean release runs at a new fixed seed. No agent code changed yet.
Next: execute that small cache experiment with direct score-equivalence tests,
strict Rust validation, and complete record comparisons; retain only if useful.

## E14 measured cache reuse

Continued from f5638d5 and implemented the recorded hypothesis: Take scoring
uses the already supplied base potential. Added exact cached/uncached score
checks over 96 seeded 2–4-player trajectories, all legal actions, both scoring
modes, and all four decision phases. Formatting, strict release Clippy, all 71
release Rust tests, and all 46 Python tests (with the pinned external reference)
pass. No version bump is needed for this score-preserving optimization.

Six serial ABBAAB release runs have identical records and 1,000 completions
each. Median runtime improves 20.9%. Fresh confirmation improves 20.7%, with
identical 999 complete/one blocked records. Preserved all reports, logs,
commands, source/binary hashes and timings under docs/results/e14-*. Retain
this measured improvement. No strength promotion or full parity claim.

Next: check the optimized profile to locate the remaining cost before choosing
another performance edit. Existing independent shared-rule comparisons remain
bounded by their documented reference exclusions and the published no-action
gap. Do not repeat rejected E9–E13 policy experiments.

## Post-E14 profile and next hypothesis

Reprofiled the fixed 112m workload at the changed source. All 10,000 full
records (including trajectory hashes) match the earlier baseline; 9,998 finish
and two remain blocked. Preserved the full sample and report. Potential remains
the largest sampled application function. Sample counts do not measure the
speedup; the separate serial E14 runs do.

Recorded E15 before code edits: cache target cost and worth across token-only
alternatives, with the original arithmetic as an exact test oracle. Planned
fresh seeds are 117m and 1,117m. Payment requires different bonuses/ownership
and must not reuse stale values. Next work is to implement and measure this
bounded cache, or reject it if the cost/benefit is poor. Goal remains active.

## E15 fixed target cache

Continued from 6a946ab. Implemented the recorded cache hypothesis only for
unchanged bonuses/ownership, leaving Payment uncached. Original potential is
the oracle. Extended the existing 96-trajectory test to compare cached base
and all legal action scores. Formatting, strict release workspace Clippy,
71 release Rust tests and 46 Python tests with pinned reference all pass.

Six serial screening runs improve median runtime by 20.8%; fresh confirmation
improves 21.0%. All 8,000 games complete. Full records and trajectory hashes
are identical within each seed. Preserved reports, logs, exact commands,
settings and source/binary hashes as e15-* evidence. Retain the optimization;
no rule, RNG or enumeration changes, engine remains v2.

Next: three- and four-player before/after comparisons with invariants enabled
at new seeds, to check behavior beyond the two-player timing workload. These
are regression checks, not a promotion or new independent-rule parity claim.

## E15 multiplayer and independent-reference regression

Both builds complete all 300 three-player and 400 four-player games with
invariants enabled. Full records and trajectory hashes match. Archived reports
and exact commands. This validates behavior outside the two-player timing
workload; one pair per player count is not a multiplayer speed claim.

Re-exported existing independent workload after E14/E15: all 5,370 complete
case payloads are byte-identical, only source metadata differs. Reran the pinned
MIT reference: 4,949 selected and 14,342 sampled branch successors still match,
with unchanged exclusions and unresolved outcomes. Saved hashes, reconstruction
recipe and summary, without duplicating the identical case payload archive.
No full parity claim or new confirmation-seed claim.

Next audit: assess cross-platform deterministic validation gaps and whether a
local second target is available. Hosted CI remains unverified because nothing
has been pushed. Do not turn one-host performance results into portable claims.

## Bounded second-architecture validation

Audited local capability: only ARM Rust target was installed, but Rosetta can
execute x86_64 binaries. Installed the pinned toolchain's x86_64 macOS standard
library, built locked release workspace, and passed all 71 tests. No project
source/toolchain settings changed for this check.

Ran x86_64 verify-report on existing ARM reports: all 1,000 two-player,
300 three-player, and 400 four-player records reproduce, including trajectory
hashes. All are complete. Saved build/test logs, exact commands, binary/input
hashes and process results. Updated architecture documentation to state this
bounded evidence, not a universal guarantee. Linux and hosted CI remain open.

Next: inspect whether the local container runtime can supply a pinned Linux
validation target without modifying project semantics or publishing anything.
If unavailable, record that limit and choose another useful project issue.

## Local Linux validation

Continued from bc85ea6. Docker CLI was installed but its daemon was stopped.
Started the local runtime and pulled the pinned Rust 1.98.1 image, recording its
digest. First attempt stopped before tests: linked-worktree Git path was absent
in the container. Retained failure evidence, then used a read-only source
snapshot excluding .git and target with separate build output.

ARM Linux passes fmt, strict release workspace Clippy, 71 release Rust tests,
and all 46 Python tests with the pinned MIT reference. Linux verify-report
reproduces all 1,700 macOS records, including trajectory hashes, for 2–4 players.
Archived logs, scripts, image/binary/input hashes and statuses. Containers exit
and are removed. No source semantics changed and nothing was pushed.

Next: audit reproducible validation automation against these now-established
cross-target checks. A reusable local command should fail if any check fails,
retain platform/source provenance, and avoid treating local success as hosted
CI evidence. Existing shell experiment scaffolding is evidence, not yet a
supported reusable validation tool.

## Promotion uses the actual Cargo executable

Continued from 9d973b6. Audit found a concrete reproducibility defect: promotion
build respected CARGO_TARGET_DIR but execution used ROOT/target/release/splendor.
A stale default binary could be evaluated after a successful custom-directory
build. Wrote a regression and confirmed failure against the old code.

The gate now reads the named binary's Cargo artifact, rejects failed/missing/
ambiguous output, and saves raw build messages plus executable path and hash.
Both benchmark and comparison use that path. Existing report/source checks
remain. All 48 Python tests pass. Full custom-directory smoke passes Rust checks,
uses the expected executable and correctly retains the baseline with two-game
screen/confirmation samples. Archived regression failure and full smoke evidence;
the random benchmark's eight blocked games remain explicit.

Next audit: gate provenance now identifies the binary, but routine validation
commands still depend on callers to retain stdout/stderr. Assess a focused
logging improvement or a higher-value uncovered rules/agent issue before adding
new automation. No rule or agent change in this step; engine stays v2.

## E16 larger fixed-budget experiment

Continued from 8a2738d. Checked E4: it tested 32/128, not 256. Recorded hypothesis,
paired setup protocol, fresh seeds and stopping rule before execution. Screen
passes with +3.7 points and no incomplete games. Fresh 20,000-game confirmation
supports +2.56 points against strong, paired 95% bounds +1.04 to +4.09 points,
while preserving unfinished outcome uncertainty. Runtime roughly doubles.

Completion worsens: 128 has one blocked game; 256 has two blocked and one capped
game. No promotion or default change. Preserved full reports, failures, hashes,
commands and runtimes. Added tested paired-budget analysis; all 52 Python tests
pass with pinned reference. No Rust, rule, agent or engine-version change.

Next: reproduce and diagnose the new 256-budget capped game (block 1508,
rotation 0, setup seed 11864268526903350202). Compare its exact record and replay
before drawing conclusions about recurrence. Prior failed E9–E13 policies remain
rejected; do not silently restore them or infer a victory from the cap.

## E16 exact cap diagnosis

Continued from 3567f9b. Adapted the historical cap harness into a reusable
source/settings-checked example supporting all player counts, unique rotation
files and short-history/no-cycle output. Exact reproduction matches all fields
of the E16 cap record. The period-four red-token suffix begins at decision 51
and lasts 19,949 decisions; search has two purchases but takes the token.
All observations except turn count return after another legal period, with no
outcome. This repeats an established failure pattern, not a new core defect.

Saved full history, hashes, diagnostic observations and validation logs. A
four-player one-decision cap smoke confirms short histories do not underflow or
produce a false cycle/winner. Formatting, strict all-target release Clippy and
71 workspace release tests pass. No agent code changed.

Next: inspect simulated continuations at the cycle's search Main phase before
writing a new agent hypothesis. Actual search repeatedly postpones a purchase;
its rollout policy is strong and may purchase on the next hypothetical turn.
Thus a naive simulated-cycle penalty may not detect the actual repeated choice.
Keep this distinction explicit; rejected E9–E13 policies remain rejected.

## E16 rollout-policy mismatch and E17 hypothesis

Continued from 2b4596f. Added an observation-based diagnostic with equal sampled
worlds per legal action, strong rollouts, and the production Engine leaf formula.
At the repeated search prefix, all 256 Take samples return to the root after two
turns, then the rollout buys. Immediate purchases do not recur. Take has the
highest estimate at horizons 8/16/32, but not 4. This is evidence of delay favored
under a simulated future policy that differs from real root search, not a claim
about exact UCB visits or game-theoretic value.

Archived traces, counts, reward summaries and harness hash. Formatting, strict
release all-target Clippy and all 71 workspace release tests pass. No agent code
changed. Recorded E17 before edits: an optional search variant assigns zero
heuristic reward when a simulated root Main observation repeats, ignoring only
turn count. Keep game outcomes and ordinary search unchanged. Development uses
known E16 case; fresh screen seed 124m and reserved confirmation 1,124m. Next:
implement that candidate, validate it, and use the gate; do not restore earlier
rejected policies or infer promotion from the development probe.

## E17 rejected after fixed-budget screen

Continued from b5dc58b and implemented only the recorded candidate. Development
probes change Take to BuyVisible(3) for all 16 seeds at depth 8, preserve hidden-
world equality, and complete the known full game in 111 decisions (a 12–15 loss).
Ordinary search exactly reproduces the prior capped trajectory. The candidate
checks recurrence at the horizon too, without changing game outcomes.

Real gate screen at fresh 124m rejects: 1,942 complete, seven blocked, 51 capped;
credit interval includes 50%. Matched search self-play has identical completion
and winner results, with only one completed record changed. All unfinished
records are identical. Saved the patch, gate decision and executable identity,
full reports, development histories, probes, hashes and logs. Confirmation
1,124m was not used. Removed candidate and restored baseline agent source.

Retained a generic observation action-probe example. Final formatting, strict
all-target release Clippy, 71 release workspace tests and 52 Python tests pass.
No default, core, engine version or replay semantics change.

Next: return to the independent parity evidence and assess the largest remaining
unsupported comparison dimension. The recent agent probes show opponent-specific
policy mismatch; do not keep extending a failed candidate to fit one case.
Existing reference exclusions and published no-action gap remain explicit.

# Web integration hypothesis (non-strength change)

Hypothesis: exposing the existing canonical `GameState` and E81 `NeuralAgent`
through a small JSON-facing WASM wrapper will preserve engine decisions while
allowing the production model bytes and champion search settings to be supplied
as assets. The wrapper must emit only the active human's observation, redact
blind opponent reservations, retain every legal payment/return/noble choice,
and report blocked games without assigning a winner. This is a product
integration change; it makes no playing-strength claim and does not change game
rules or search defaults.
