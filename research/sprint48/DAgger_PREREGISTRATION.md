# Sprint 48 learner-state label pilot

## Hypothesis

The first-stage one-hot Entity policy may make choices in states that are rare
in its training corpus. A fresh AlphaZero800 search at those states may provide
better action labels. This pilot tests data quality and short-fit value. It does
not assume that the new labels improve strength.

## Data and labels

Use complete native evaluation records from the frozen first-stage learner
descriptor. The candidate actions stay unchanged. Run the source records
through the sprint evidence summarizer before selecting any blocks. This checks
the complete index sequence, both rotations, and duplicate full setup IDs.
Also check setup IDs after the native low-32-bit seed conversion. Replay each recorded action
and chance seed from the initial state. Check the public observation hash and
every after-state hash. At each candidate turn, query a new AlphaZero root with
800 simulations. Store its best legal action and selected-action root Q.
Store the candidate's final credit as the outcome label.

The training row contains sampled features from the candidate's public
observation, the legal-action mask, the AlphaZero action, its Q credit, and the
candidate's final credit. The full referee state goes to the offline teacher
only. It does not go to the learner feature encoder. The actor action and
teacher action are both kept in the compressed audit file.

Use complete paired seat rotations only. If either rotation is incomplete,
replay both records and write no labels for that setup. Do not convert an
unknown result to a loss, draw, or win. Keep one setup ID in one split. Use
different source masters for training and development. Exclude setup IDs from
the existing train and dev corpus before fitting.

## Bounded commands

The source schedule must use the pinned native profile, the exact learner
descriptor hash, and unchanged AlphaZero800. Start with one paired setup.
This creates at most a finite number of teacher searches. The pilot does not
start games or fit a model.

```sh
local/strength/inference/bin/python research/sprint48/learner_data.py \
  --input local/research/sprint48/external-00/arena/games.jsonl \
  --learner-descriptor local/research/sprint48/external-00/service/13/model.bin \
  --policy-binary local/research/sprint48/external-00/binaries/native_policy_worker \
  --strength-binary local/research/sprint48/external-00/binaries/strength_worker \
  --output local/research/sprint48/dagger-train-pilot-00 \
  --split train --max-blocks 1 --workers 1 --worker-index 0 \
  --teacher-master 17711000001 --feature-master 17711000002 \
  --exclude-setup-ids local/research/sprint48/dagger-train-excluded-setup-ids.txt \
  --invariance-checks 1
```

The two binary copies are frozen in the trial directory. The pilot manifest
records both paths and hashes. The policy-binary hash must match the source
schedule. The strength binary must report the same source ID as the schedule.
If source metadata has a strength-binary hash, the script also checks it.
The current trial schedule does not contain that hash, so the manifest marks
that source hash as absent. The pilot output is training data from then on;
never use its setup IDs for played evaluation. The script rejects the sealed
final external master.

For the current trial 00 files, the descriptor SHA256 is
`914cbd5c9f831739f556ef031d11f3a048c57770a0223953476ab15a51d549c1`, the
policy worker SHA256 is
`42583d6f6ef6126402a535f29a87e69e5a6249741b8a8b1dabceb73171a2e2de`, and the
strength worker SHA256 is
`777e63c064a59be5da8a9ca6ba43afc9d1153bcf0171b1eb244a5e81866d51a2`.
The raw schedule SHA256 is
`0d1fb4501178daf90b59249daf2084fa88950be672ad77ddbae6ac7464836cd5`.

For a separate development shard, use a different source schedule, source
master, feature master, and teacher master. Pass an exclusion file that
contains the existing development IDs and every setup ID in the new train
shard. Do not reuse the example masters above. Stop after this pilot until the
campaign owner checks runtime, label balance, and the retained manifest.

For a larger run, choose a new `--max-blocks` before launch. Set
`--workers N` to split those leading blocks by `block % N`; each worker writes
its own output directory. Do not combine shards from different descriptors,
source profiles, or split IDs. The manifest contains `registry_entry`, which
can be added to a copied expanded-data registry after its hashes and setup
IDs pass review.

## Checks and stop rules

- The descriptor hash must match the candidate hash in the source schedule.
- The source AlphaZero revision, checkpoint, profile, and 800-simulation
  setting must match this plan.
- Every paired source record must replay to its recorded state hashes, terminal
  reward, and score. Any mismatch stops the run and invalidates the shard.
- Every teacher action must be legal and have a completed root visit. Any
  failed or incomplete teacher search stops the run.
- Public inputs must remain identical across eight independent sampled hidden
  worlds for each checked learner observation. Any difference stops the run.
- The shard must have no setup-ID overlap with either training or development
  data. Any overlap rejects the shard.
- Keep one seed-master split for fitting and another for development. Do not
  tune against the final external master.
- Fit only after this pilot passes. Compare the candidate checkpoint with its
  frozen parent on the same development data and then on fresh fixed-budget
  paired games. Promote only on the registered outcome rule; lower training
  loss alone is not evidence of stronger play.

## Risks

The teacher cost is 800 AlphaZero simulations at every candidate decision.
The pilot may take too long for this sprint. It also labels states from a
fixed candidate-versus-AlphaZero trajectory, so it may not cover states reached
after the candidate changes its policy. Root Q values are estimates and may be
poorly calibrated. The final candidate reward is noisy. Keep the pilot small
until measured throughput supports a larger shard.
