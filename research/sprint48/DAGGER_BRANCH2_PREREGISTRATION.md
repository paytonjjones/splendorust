# Branch two: learner-state DAgger fit

Status: prepared only. Do not collect games or fit until the campaign owner
approves branch two after the current search control ends. The root plans to
launch source collection after control 04 unless results support stopping this
line of work.

## Question

Does AlphaZero800 relabeling on states reached by the frozen `refit-01`
candidate improve native play when it is mixed into the full expanded training
stream? The parent is always the selected `refit-01` checkpoint, SHA256
`44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f`.
Search-control results do not change this parent. The campaign owner can defer
branch two if a control supports stopping this line of work.

The trial-00 labels are excluded. They use the first-stage descriptor, while
this branch uses the frozen `refit-01` descriptor. This keeps the learner
that generated the source states fixed within this fit.

## Data

Freeze one runtime descriptor and record its hash. Use that same
descriptor in both source schedules and label runs. Freeze and record the
policy-worker and strength-worker hashes. Keep the AlphaZero revision,
checkpoint, native profile, and 800 simulations per candidate decision
unchanged.

Use the following finite schedules:

| Split | Source master | Games | Paired setups | Candidate search |
| --- | ---: | ---: | ---: | --- |
| Train | `17710000000` | 1,024 | 512 | Gumbel128, depth 16, 3 sampled worlds, cap 16 |
| Dev | `17720000000` | 256 | 128 | Gumbel128, depth 16, 3 sampled worlds, cap 16 |

Use distinct teacher and feature masters for train and dev. Record the chosen
values before launch. Proposed label masters are `17711000011` (train
teacher), `17711000012` (train feature), `17721000001` (dev teacher), and
`17721000002` (dev feature). They differ from each source master and each
other. Use `run_labels.py` only after `evidence.summarize` confirms every
source record and paired block. Require all requested games to be complete.
Any incomplete, duplicate, or invalid record stops that source.

The source collector takes one frozen checkpoint and one exclusion file. That
file must contain the old corpus IDs, the trial-00 pilot and full-label IDs,
every consumed campaign schedule (including a running schedule), and validation
IDs. For consumed runs, derive every planned setup ID from the registered
master and game count. Do not infer exclusions from partial raw records. The
collector checks the new source IDs against this file before labeling. Save this
file as `local/research/sprint48/dagger-branch2-excluded-setup-ids.txt` and
record its hash.

Before collection, build and inspect the fixed exclusions. `--prepare` writes
the sorted list once. `--check` reads the same registries and campaign records
and checks the proposed 512/128 setup IDs against exact and native low-32-bit
exclusions. It does not write files or start game workers:

```sh
local/strength/inference/bin/python research/sprint48/prepare_dagger_branch2.py --prepare
local/strength/inference/bin/python research/sprint48/prepare_dagger_branch2.py --check
local/strength/inference/bin/python research/sprint48/collect_dagger_sources.py \
  --checkpoint local/research/sprint48/refit-01/fit/model.pt \
  --exclude-setup-ids local/research/sprint48/dagger-branch2-excluded-setup-ids.txt \
  --check
```

The checked exclusion file contains 32,322 IDs. Its SHA256 is
`d115569b66a621d0fd3d6802e2e240c5b207483527d6439011d6d655fb4a2ba3`.

The collector pins the refit-01 checkpoint SHA and all three executables in
`local/research/sprint48/build-controls/release/examples`. Its check also
requires the saved public native-profile compatibility receipt. It records the
frozen Rust source copies and binary hashes from `external-02`, which produced
these executables. It keeps those compiled sources separate from the current
collector and runner Python source snapshot. Each schedule shard must accept
and report the requested Gumbel128 settings before it writes game records.
The final-campaign context is not used for these training-source games. The
collector copies `campaign_context.py` with the other imported native runner
sources so the source snapshot is complete.

After the current search control ends and the root approves collection, use:

```sh
local/strength/inference/bin/python research/sprint48/collect_dagger_sources.py \
  --checkpoint local/research/sprint48/refit-01/fit/model.pt \
  --output local/research/sprint48/dagger-branch2-sources \
  --exclude-setup-ids local/research/sprint48/dagger-branch2-excluded-setup-ids.txt \
  --binary-directory local/research/sprint48/build-controls/release/examples
```

The collector uses MPS, service batch 64, and 64 schedule workers. It copies
and hashes the policy and strength workers. It writes both schedules, replays,
evidence summaries, source IDs, and process records. It does not label or fit.
It does not edit `RUN.json`.

Teacher labels are one-hot AlphaZero800 best actions, selected-action root Q,
and final candidate credit. Keep private referee state inside the offline
teacher. The learner features must use the public observation only.

Keep the existing train and full-dev registry entries unchanged. Create a
branch-local copy of the registry. Add only these parent-refit train labels to its
new DAgger train group and these held-out labels to a separate DAgger dev
group. Exclude the existing corpus IDs and all branch-two train IDs from dev.
Check exact 64-bit IDs and native low-32-bit IDs. Do not use final masters.
Played evaluation records never enter either split.

## Fit

Start from the frozen `refit-01` checkpoint. Keep the Entity architecture,
optimizer, learning rate, batch size, seed, and two-epoch limit unchanged.
Keep 512 rows from the full base stream in each update and append 57 DAgger
rows sampled with replacement. Weight the mean base loss by 0.90 and the mean
DAgger loss by 0.10. The sampled-row share is 57/569 = 10.02%. This keeps all
base examples and optimizer steps and adds about 11.1% more examples per step.

The expanded base stream has 1,682,022 rows. It uses about 3,286 base batches
of 512 per epoch before per-shard final batches. If the train labels contain
about 28,600 rows, the fit will draw about 187,300 DAgger rows per epoch, or
about 6.6 draws per unique row. Use the actual registry row counts and actual
batch count in the fit receipt.

Use this 10% mixture because the completed native screens remain weak and the
fit needs clear pressure toward the learner's own state distribution. A 1%
mixture gives little weight to these labels. This one fit adds about 11.1%
examples to each unchanged base update. Do not change its mixture after
looking at dev results.

## Fixed selector and stop rules

Evaluate epoch zero, epoch one, and epoch two on both fixed dev groups. For
each group, compute policy cross-entropy plus four times outcome Brier score.
Compute each group score separately, then select by:

`0.90 * existing_full_dev_score + 0.10 * new_dagger_dev_score`

Epoch zero can win. Keep the existing full-dev and new DAgger-dev metrics
separate in every report. Do not change the weights or inspect played
evaluation results before checkpoint selection.

Stop before fitting if descriptor hashes differ, teacher or worker identity
differs, source completeness fails, any data check fails, or either exact or
low-32-bit setup IDs overlap. Stop the fit on a non-finite loss or gradient.
Promote only after the fixed selector passes and fresh, paired native
confirmation supports a strength gain. Lower dev loss alone is not a strength
claim.

## Cost and limits

At the audited trial-00 mean of 55.8 rows per setup, the schedules may produce
about 28,600 train rows and 7,100 DAgger-dev rows. The frozen refit trajectory can
have a different length, so manifests decide the actual counts. Trial-00 label
runtime was 52.4 seconds for 63 setups on eight workers. This suggests teacher
labeling is small relative to game collection, but it is not a promise for
these schedules. The schedules contain 640 paired setups and 1,280 games in total; they may
take much longer to play. No schedule or fit has started under this plan.

`run_labels.py` labels the source records on CPU with eight workers, after
collection completes. Use separate output directories for the two splits.
For dev labels, pass the train-label registry as `--prior-manifest`. This
checks for split overlap again by full and native low-32-bit IDs. Do not change
the current trainer or shared data registry. Build a branch-local copied
registry and trainer only after the root approves this branch and freezes the
runtime descriptor. The copied trainer is [branch2_train.py](branch2_train.py).
The finite fit wrapper is [run_branch2.py](run_branch2.py); it checks the fixed
refit-01 checkpoint, label source hashes, setup-ID isolation, active campaign
state, and deadline. It writes its own receipts and does not edit `RUN.json`.
After the label registries are complete, check the fit plan without starting
MPS training by adding `--dry-run` to:

```sh
local/strength/inference/bin/python research/sprint48/run_branch2.py \
  --dagger-train-registry local/research/sprint48/dagger-branch2-train-labels/registry-entries.json \
  --dagger-dev-registry local/research/sprint48/dagger-branch2-dev-labels/registry-entries.json \
  --dry-run
```

The fixed label commands are:

```sh
local/strength/inference/bin/python research/sprint48/run_labels.py \
  --input local/research/sprint48/dagger-branch2-sources/train/arena/games.jsonl \
  --learner-descriptor local/research/sprint48/dagger-branch2-sources/service/13/model.bin \
  --policy-binary local/research/sprint48/dagger-branch2-sources/binaries/native_policy_worker \
  --strength-binary local/research/sprint48/dagger-branch2-sources/binaries/strength_worker \
  --output local/research/sprint48/dagger-branch2-train-labels \
  --split train --max-blocks 512 --workers 8 \
  --teacher-master 17711000011 --feature-master 17711000012 \
  --exclude-setup-ids local/research/sprint48/dagger-branch2-excluded-setup-ids.txt

local/strength/inference/bin/python research/sprint48/run_labels.py \
  --input local/research/sprint48/dagger-branch2-sources/dev/arena/games.jsonl \
  --learner-descriptor local/research/sprint48/dagger-branch2-sources/service/13/model.bin \
  --policy-binary local/research/sprint48/dagger-branch2-sources/binaries/native_policy_worker \
  --strength-binary local/research/sprint48/dagger-branch2-sources/binaries/strength_worker \
  --output local/research/sprint48/dagger-branch2-dev-labels \
  --split dev --max-blocks 128 --workers 8 \
  --teacher-master 17721000001 --feature-master 17721000002 \
  --exclude-setup-ids local/research/sprint48/dagger-branch2-excluded-setup-ids.txt \
  --prior-manifest local/research/sprint48/dagger-branch2-train-labels/registry-entries.json
```
