# Sprint 48 training diagnostic

Status: read-only inspection and a short CPU evaluation. No trainer, build,
service, or game was started here. The sprint is active in `RUN.json`; the
selected final seed remains sealed.

## Finding

If the first native comparison is weak, the best low-cost training branch is
the data-reuse fit already listed in `README.md` section 4: start from the
current one-hot candidate and refit for two epochs on the expanded corpus.
This is a targeted check for native-policy drift after canonical-only
fine-tuning. Do not add a new value calibration step or switch back to richer
visit/Q labels based on these results.

The frozen Entity checkpoint was trained from scratch on 1,682,022 rows from
30,000 setups: 1,403,544 native rows from 25,000 AlphaZero800 expert games and
278,478 canonical rows from 5,000 E81 expert games. Its held-out set has
111,572 rows from 2,000 disjoint setups: 55,926 native and 55,646 canonical.
The sprint one-hot candidate instead had one 111,065-row canonical-rich fit
set and a 22,283-row canonical-only dev set. It selected epoch 1; epochs 2–4
raised its registered dev score. This creates a clear native distribution
shift risk even though the candidate starts from the frozen Entity parent.
The compared checkpoints are bound by `ready.json`: frozen Entity
`cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84` and
one-hot runtime `ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
The expanded corpus registry SHA256 is
`4dd2f1a9c8f9e78a192a10da1c686dac3481e76c45a4034a931fae61a4eca581`.

The 525 learner inputs contain public features and a native/canonical profile
flag. The expanded corpora keep the two profiles separate in development
metrics. The existing trainer also keeps teacher policy labels and the value
targets, selects by policy cross-entropy plus four times outcome Brier, saves
each epoch, and resets AdamW for a parent run. The generation-one one-hot
screen beat original Entity in 2,000 canonical games, but that does not
establish a result against AlphaZero800.
The original 12-epoch full-corpus Entity fit took about 8,990 seconds, so two
epochs suggest about 25 minutes of MPS fit time. This is a scale estimate from
the earlier fit, not a measured duration for this parent or current host.

## Short CPU dev check

I loaded the frozen Entity baseline and the sprint one-hot runtime checkpoint.
I evaluated a deterministic, evenly spaced 4,096-row sample from each held-out
profile, using four CPU threads. This took 7.8 seconds. It used the model's
masked logits, one-hot expert action labels, terminal outcomes, and saved
teacher values. The policy column is `KL(one-hot expert || model policy)`,
which equals one-hot negative log likelihood. Value prediction is converted
from the model's signed output to a win probability. The mixed-target Brier
uses `(teacher + outcome) / 2` where teacher values are finite.
The code restored each profile's 4,096 indices at evenly spaced positions
across the profile's concatenated development rows. It did not write data or
modify checkpoints.

| Held-out profile | Checkpoint | Policy KL / NLL | Action top-1 | Outcome Brier | Mixed-target Brier |
|---|---|---:|---:|---:|---:|
| Native | Frozen Entity | 1.24538 | 57.72% | 0.20927 | 0.06445 |
| Native | Sprint one-hot | 1.32977 | 56.67% | 0.20794 | 0.06317 |
| Canonical | Frozen Entity | 1.48464 | 49.80% | 0.20849 | 0.06451 |
| Canonical | Sprint one-hot | 1.60819 | 49.49% | 0.20592 | 0.06198 |

This small sample supports the drift hypothesis for action policy. It shows no
matching value-calibration failure: the candidate has slightly lower Brier
scores, and the five-bin predicted-win-rate check is close for both models.
The sample is position-weighted, contains related positions from each setup,
and has no confidence interval. It is diagnostic evidence only. It does not
replace full-dev metrics, and it says nothing about playing strength.

## Finite refit and safeguards

Use the prepared command from the sprint runbook only if the first native
comparison gives a reason to spend this time:

```sh
python3 research/entity_baseline/bootstrap.py --native-upstream
local/strength/inference/bin/python research/architecture_pivots/train.py \
  --kind entity \
  --parent local/research/sprint48/ready/first/onehot/runtime.pt \
  --data-scale expanded --epochs 2 --batch 512 --device mps --fast-entities \
  --output local/research/sprint48/refit-01
```

The corpus has 30,000 train setups and 2,000 separate dev setups. Do not use
the live external comparison records, the 17.7-billion final master, or any
final games for fitting or checkpoint selection. Keep the frozen baseline and
current one-hot checkpoint as controls. Review native and canonical policy
cross-entropy, action accuracy, terminal Brier, mixed-target Brier, and each
epoch's checkpoint. Export and run the real-position parity check. Then use a
new exploratory master to compare the selected refit with the unchanged
AlphaZero800 at the same declared search budget. Keep the final candidate and
sample count frozen before opening the final master. Reject the branch if it
only improves held-out loss without improving the external game result.

This tests replay of an existing mixed native/canonical expert corpus. It does
not add teacher games, change the public inputs, or establish that AlphaZero's
native rules and canonical Splendorust rules are interchangeable.
