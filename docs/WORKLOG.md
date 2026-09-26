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
