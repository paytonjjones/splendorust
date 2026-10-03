# Sprint 48 policy/value ensemble hypothesis

## Hypothesis

The refit checkpoint has lower held-out policy cross-entropy than its one-hot
parent, while its outcome Brier score is higher. A self-contained ensemble may
keep the refit's policy logits and average its signed two-player values with
the one-hot parent's signed values. This may improve the value estimate without
changing the chosen policy. It is an inference-time hypothesis only. It does
not predict a strength gain.

## Frozen members and behavior

- Policy and first value member: `local/research/sprint48/refit-01/fit/model.pt`,
  SHA256 `44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f`.
- Second value member: `local/research/sprint48/ready/first/onehot/runtime.pt`,
  SHA256 `ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
- Policy output is exactly the refit member's logits.
- Value output is the arithmetic mean of the two signed value vectors.
- The packed checkpoint embeds both state dictionaries and both source hashes.
  It does not need the source files at inference time.

Each Entity member has 4,780,883 parameters. The packed model has 9,561,766
parameters. It runs two full trunks for each batch, so plan for about twice the
single-model inference compute and latency. The exact cost depends on batch
size and device. Both members receive the existing `fast_entities` runtime
setting.

## Check and limit

`research/sprint48/make_ensemble.py` packs the frozen members and checks 32
public development inputs on CPU. It requires exact equality for policy logits
and for the value arithmetic mean. This checks model wiring only. Export and
service parity must pass before any evaluation. Do not use the pack helper to
start games or to select a model. Any later strength test needs fresh paired
whole games, fixed search settings, and complete status accounting.
