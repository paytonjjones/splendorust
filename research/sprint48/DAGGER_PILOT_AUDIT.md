# Sprint 48 DAgger label audit

The pilot and full trial-00 label run passed the read-only audit. See
[DAGGER_TRIAL00_LABELS_RECEIPT.json](DAGGER_TRIAL00_LABELS_RECEIPT.json) for
hashes and checked fields.

The source schedule has 128 complete games and 64 paired setups. The pilot
labelled one setup with 54 rows. The full run skipped that setup and labelled
the other 63 setups in 3,516 rows. The combined training set has 64 unique
setups and 3,570 rows. No setup was added twice. No games were run for this
audit, and no fit was run.

Every binary row has the expected 2,232-byte `DTYPE` layout. The full run
features have shape `(3516,392)`, the legal mask and teacher policy have shape
`(3516,81)`, context has shape `(3516,7)`, and packed public input has shape
`(3516,525)`. Values are finite. Masks and policies are binary. Every teacher
policy has one legal action, and each recorded actor action is legal. Terminal
credit matches the candidate seat in the source games. Rebuilding every packed
input from features and context gives an exact match. The full run records 64
successful eight-world public-input checks; the pilot records one more. These
checks sample states and do not prove every possible hidden-world case.

The actor and AlphaZero actions differ on 1,682 of 3,570 rows (47.1%). The
combined outcome labels are 1,910 rows with candidate credit 0, 28 rows with
credit 0.5, and 1,632 rows with credit 1. The pilot's two games both gave the
candidate full credit. These are source-trajectory labels, not a strength
result or a calibration result.

The full label run took 52.4 seconds across eight workers. It labelled 3,516
rows from 63 setups. This measured time is for teacher labeling only. It does
not include game collection or model fitting. The pilot took 14.95 seconds for
54 rows in one setup. Do not project the pilot's single-worker rate onto the
eight-worker result.

The pilot and full run have no exact or native low-32-bit setup-ID overlap.
Neither overlaps the 32,000 setup IDs already excluded from training. Trial
00 and its labels are training data only from this point onward. Do not use
trial-00 records for development or played evaluation.

The revised branch-two plan is
[DAGGER_BRANCH2_PREREGISTRATION.md](DAGGER_BRANCH2_PREREGISTRATION.md). The
collector is [collect_dagger_sources.py](collect_dagger_sources.py). Neither
source collection nor fitting has started.
