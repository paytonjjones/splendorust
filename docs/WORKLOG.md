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
