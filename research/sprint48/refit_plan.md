# Sprint 48 expanded-corpus Entity refit preregistration

Registered before fitting. This is training branch 1 of at most 2 in the
48-hour sprint. It tests whether the one-hot candidate's weaker native-policy
fit is caused by canonical-only adaptation. The completed 128-game external
screen for the current candidate is retained as exploratory evidence; it does
not alter this recipe or open any final seed.

## Fixed intervention

Warm-start from
`local/research/sprint48/ready/first/onehot/runtime.pt` (SHA256
`ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`). Run
the existing Entity trainer once on all expanded training rows for exactly 2
epochs, batch 512, MPS, `--fast-entities`, and fresh AdamW. The command and
source hashes are recorded by `run_refit.py` before it starts the trainer.
The wrapper owns the new receipt directory
`local/research/sprint48/refit-01`; the trainer receives its new child path
`local/research/sprint48/refit-01/fit` because the trainer creates its output
directory with `exist_ok=False`. No existing run receipt or checkpoint is
overwritten.

The fixed corpus registry is
`research/entity_baseline/expanded-data.json` (SHA256
`4dd2f1a9c8f9e78a192a10da1c686dac3481e76c45a4034a931fae61a4eca581`): 30,000
train setups and 2,000 disjoint dev setups, with native and canonical source
rows retained in their registered splits. The wrapper checks the prepared
registry against this registry and records each input path and declared hash.
The bootstrap receipt already verified the 408 source files before this
registration.

## Selection and decision

Do not change the trainer's existing full-dev selector: minimum registered
`policy CE + 4 * outcome Brier`, across native and canonical dev metrics.
Use its `model.pt` as selected and preserve `latest.pt`, `manifest.json`, and
the per-epoch metrics under the `fit` directory. The trainer does not promise
separate checkpoint files for every epoch. If the trainer does not finish,
retain partial artifacts and mark failure or deadline stop. Do not resume in
place.

This fit can establish a held-out imitation improvement only. Do not promote
from loss alone. Export/runtime parity must pass, then use a fresh exploratory
master at the registered AlphaZero800 profile and equal search budget. Keep
all game statuses and unknown outcomes; do not use external game records for
training or selection. Final seed masters stay sealed until a candidate is
frozen.

## Resource and stop limits

Run only after the MPS inference service and other GPU jobs have stopped. The
wrapper records its PID, trainer PID/process group, exact command, input/source
hashes, deadline, logs, manifest, exit status, and failures. It stops the
trainer at the existing campaign deadline and preserves partial outputs. Do
not extend the two-epoch fit or launch another copy to improve a result.
