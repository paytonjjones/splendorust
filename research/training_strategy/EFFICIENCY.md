# Controlled cap-randomization comparison

This protocol is registered before any cap-randomization data or model result.
It follows the label and second-generation comparisons. It changes only the
per-position search cap. It adds no architecture, noise, early stochastic move,
symmetry or search-setting change at evaluation.

Hypothesis: cheap moves between full-search training positions provide more
episode diversity per generation budget, and improve strength per compute.
The pilot already measures 310 seconds per 64 full-search games at 32 workers.
The extrapolated first train/dev cost is 3.2 hours. This is enough to warrant
a controlled efficiency test; neither that estimate nor an inference probe
is evidence that cap randomization improves strength.

Use the selected generation-one model as the teacher and training parent.
The full-search control is the checked second-generation `iterative` arm.
Keep its common development corpus, 50/50 recent replay, label rule, optimizer,
seed, four epochs, row/update budget, and checkpoint-selection criterion.

First collect two excluded 64-game cost pilots with the selected teacher:
both use setup master 5480000000 and policy master 9480000000. One has full
PUCT256 at every position. The other chooses full256 with probability 0.25
and cheap64 otherwise. Only full-search positions with complete terminal
outcomes train. Keep cheap, fallback and incomplete rows for cost/accounting.
Replay every game. The pilots are diagnostics, not training or strength games.

For training, retain the full control's setup master 5440000000 and policy
master 9440000000. Collect cap-randomized games in ordered 64-game chunks,
adding each chunk offset to both masters. Stop once actual model inference
calls reach the full control's `iterative-data/complete.json` call count.
Keep and account for the whole last chunk. Do not discard paid work or select
episodes by winner. This budget is fixed before PCR collection and does not
depend on any PCR strength result. Use at most 20,000 games; preserve failure
receipts and data if the bound is reached or call overshoot exceeds 2%.

The resource match is **useful model inference calls**, not isolated GPU time
or equal FLOPs. Both arms use the same model, 32-row service, 32 workers and
search profile. Record total simulations, actual collector/wall seconds,
eligible full targets, games, bytes, and shared load. Batch padding, tail time,
host load and changed episode lengths can cause a wall-time difference. Do
not call this an equal-wall-time comparison. Report actual time-based gain
per compute as well as the matched-call result.

Start the fit from the same generation-one full checkpoint used by the full
control. Use 50% generation-one replay and 50% PCR data, with exactly the full
control's `epoch_rows`. Reuse the second study's frozen-teacher development
data and the common epoch selection. This holds fit updates constant even if
PCR supplies fewer full targets and requires sampling with replacement.

Run two fresh paired 2,000-game canonical comparisons:

- PCR versus full-search generation two: master 5481000000.
- PCR versus original frozen Entity: master 5482000000.

Both use the existing Gumbel128/depth16/pool3, 32 workers, root-noise zero,
all seat rotations and `scripts/promote.py`. Recompute intervals from game
records. A supported PCR benefit requires no unfinished games and lower 95%
credit above 51% in the direct PCR/full comparison. Keep negative/ambiguous
results. A faster pilot alone cannot support a strength claim. No automatic
champion update is allowed.

This isolates cap randomization at a matched inference-call generation
budget. A lower-cost, fixed-episode-count PCR fit, staged budgets, noise,
stochastic opening moves and symmetry remain untested by this comparison.
Do not assign any result to those features.

Run only after the first and second studies finish and their records are
checked. The controller uses the same exclusive study lock and a new output:

```sh
local/strength/inference/bin/python research/training_strategy/run_efficiency.py --first local/research/training-strategy/first --second local/research/training-strategy/second --output local/research/training-strategy/efficiency
```
