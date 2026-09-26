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

Next useful research issue: the search/strong workload found a blocked game
at setup seed 18,210,048,530,404,438,792, rotation 0. Preserve its replay and
inspect whether search values blocked rollout leaves too favorably. Any agent
change needs a written hypothesis, a fixed development screen, and fresh
confirmation seeds. Do not confuse this with a core rule failure.

## Remaining boundaries

Parity is bounded to the documented shared rules and sampled states. The
reference differs on blind reservations, payment/return choices, reduced takes,
a color-card cap, forced pass, tiebreak scoring, and hidden information. There
is no full-engine equivalence claim. No-action positions remain unresolved by
the publisher rules and have no assigned winner. Fresh confirmation seeds are
still the researcher's responsibility; new output directories do not prevent
reuse of a holdout in a different directory.
