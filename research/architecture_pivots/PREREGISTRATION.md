# Major architecture pivots

Cost refinement, registered after the original measured cost ratios are known:
all three original estimated matches miss the +/-20% target. Retain them.
Use 128-game timing-only calibrations on fresh native setups. Test residual
budgets 4/5/6 against E81 at 128, and Entity/history policy-only against E81
at 320/384/448. Select the smallest absolute log response-cost ratio; ignore
calibration strength. Run one fresh 2,000-game native screen per selected
budget pair, with 14 workers and the same batch-32 MPS backend. Report actual
ratios and mark any final mismatch explicitly. `cost-refinement/PLAN.json`
records the fixed grids, fresh masters and timing dependency. Hold only the
waiting canonical confirmation controller until these cost measurements end.
No active fit or match is stopped; native confirmation finishes first.

Cost-refinement correction, registered before any corrected pilot: the first
refinement retained one 128-game pilot, then failed on the report field
`worker_sha256` (the actual native field is `binary_sha256`). Keep the failed
source, pilot and logs. Exclude that pilot from selection. The canonical
controller resumed before correction; its active match continues. The
corrected `cost-refinement-v2/PLAN.json` uses fresh calibration master
5370000000 and strength master 5380000000, with fixed model/pilot offsets.
It keeps the same grids, timing-only selection and budgets. It waits for both
confirmation controllers to complete, with no controller holds or signals.
This supersedes the first plan's sequencing and seeds only.

User-directed promotion-policy amendment P2.1, 2026-10-02, after the expanded
history/E81 result but before future stages: replace the any-unfinished-game
veto with the registered `bounded-no-action-v2.1` rule. Allow at most 1%
`no_legal_action` games per stage. Keep every requested game and seat rotation;
the lower confidence bound gives unknown outcomes zero candidate credit and
the upper bound gives one. No raw outcome becomes a draw, loss or winner.
Decision-limit games, invalid reports and execution errors still reject the
stage. Keep the paired confidence method, one-point promotion margin, all
checkpoints, budgets and fresh seed streams. The user requested this change;
it is not a preregistration of the known history result.

Apply it to all preserved canonical screens with separate, hash-bound
reassessments. Select the milestone model from policy-valid screens by
worst-case credit over all requested games, retaining the fixed model index
and confirmation seeds below. The history attribution/parent milestone
trigger accepts policy-valid canonical evidence with lower bound above 50%.
Native completion rules are unchanged. Restart only the two waiting drivers
that contain the old completion filter; preserve their original plans and
record new policy receipts. The running parent screen finishes under its
loaded old gate and can then receive a separate reassessment. No training or
match is interrupted for this amendment. E81 stays the champion.
See `promotion-policy-v2/REGISTRATION.json`, `AMENDMENT.json` and the
immutable reassessment files. The initial 0.1% registration was increased to
1% at the user's request before new stages ran.

User-directed control stop, 2026-10-02, before expanded history strength tests:
stop the expanded Entity parent continuation after 10 complete epochs, during
epoch 11. All completed dev scores worsened; the selected checkpoint remains
epoch 0 and its state tensors equal the frozen Entity parent bit for bit.
Preserve the original 12-epoch plan, manifest, latest complete checkpoint and
an explicit early-stop receipt. The full history fit remains 12 epochs with
selected epoch 1. Continue every registered strength, attribution, cost and
confirmation test with the existing seeds and budgets. Call the parent an
early-stopped continuation control, not a completed equal-budget fit.
The evaluation resumer retains the original helper definitions and exact
post-training commands. This is a user-requested budget change, not a new
checkpoint selection rule or architecture change.

History parent infrastructure update, before expanded base results: if the
registered selection chooses the residual, extend that exact residual with
a four-layer width-256, eight-head Transformer over its state embedding
and the same 16 public history tokens. Total parameters: 8,318,898. Initialize
the history-to-state and auxiliary feedback projections to zero. CPU and
MPS checks must preserve parent policy/value outputs bit for bit before
training, and confirm that public pool/tier masks constrain beliefs.
Use the same version 2 history, ground-truth labels, auxiliary weights,
12 extra epochs and equal-budget residual continuation. This avoids an
entity-only assumption. If it gains, the same architecture history-only and
state-only auxiliary controls remain required before attribution. Its extra
capacity must not be called a history benefit without those controls.

Final confirmation rule, fixed before expanded fit and strength results:
after the expanded 2,000-game canonical screens, select the completed
champion comparison with the highest candidate credit among the four base
controls and full history model. If it has at least 48% credit and its upper
95% bound reaches 50%, or its lower bound exceeds the promotion margin,
run a fresh 2,000-game screen plus 20,000-game confirmation through
scripts/promote.py. Use master 5220000000 plus the selected model's fixed
index times 100000 (small 0, cold small 1, residual 2, entity 3, history 4).
The confirmation uses the tool's separate master plus 1000000000. Preserve
the original screens. Do not use pilot strength to select search budgets.
Also confirm a supported full-history gain over equal-budget parent
continuation after attribution controls, at master 5230000000 with the
same separate confirmation offset. Clear losses need no 20,000-game run.
These tests report evidence; they do not automatically change the champion.
Apply the tool's validity and regression guards to the new screen. If one
of these guards stops confirmation, retain that failure and its raw results.

Worker scaling update: a fresh 128-game policy-only check and 32-game
Gumbel128 check compare 14 and 32 game workers using the same frozen entity
and E81 models. Ordered records and trajectory hashes match exactly in both
checks. Shared-host full-search time falls from 297.80 to 155.29 seconds.
Keep the running 14-worker screen. Use 32 workers for later canonical screens
and include 32 in final scaling measurements. Keep native strength and
cost-matching trials at 14 workers. This changes concurrency only, with the
same registered seeds, models, search iterations and depth. These small
worker checks are infrastructure pilots, not playing-strength evidence.

Date: 2026-10-01. Parent: 120d12d. Champion: frozen E81 Gumbel128,
SHA256 e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8.
Keep engine v2 and GitHub Actions unchanged. No champion update without the
promotion gate. Keep failed trials and all incomplete games.

H1: The small network limits fit and play. A deep residual network with 10–50
times its capacity, the same public state and policy/value targets, will reduce
held-out error and increase fresh-seed strength. Use width 512, eight residual
blocks with two dense layers each (about 4.5M parameters). This is a full trained
network, not a correction over a frozen small leaf model.

H2: Relational encoding limits fit and play. A six-layer width 256, eight-head
Transformer with feed-forward width 1024 (about 4.8M parameters) over semantic
bank, player, market, noble, reservation and deck tokens will beat the residual
network under matched training data, targets, updates and search budgets.
Preserve every public field, reservation flag and public rules identity.

H3: Missing public history and learned hidden-state inference limit play. Extend
the most promising full network after the first two trials. Use at most16
preceding public action tokens. Train next-opponent-action and hidden reservation
identity heads from replayed simulator ground truth. Ground truth is label-only.
Build tokens before the current action, without setup ID, chance seeds, future
actions or hidden reservation identities. Include matched history-only,
auxiliary-only and no-history inference ablations where feasible. Condition
hidden beliefs on the legal unseen-card pool. Never use a real deck order.

Reuse all E95 train/dev archives, plus the fixed E87 canonical dependencies:
336,502 training rows and 111,572 development rows, with disjoint setup IDs.
Run the E95 small public model control on the same data. Train large models
from fixed seed 800000031; small control starts at E81. Use 12 epochs, batch 512,
AdamW, gradient clipping 5, cosine decay, weight decay 1e-4. Initial learning rate
3e-4 for new models and 1e-4 for the warm small control. Select checkpoints by
dev policy CE +4 outcome Brier. Report both native and canonical metrics.
Equal data and updates do not imply equal FLOPs or equal initialization.
Excluded pilot runs may test infrastructure and tune only numerical stability.
Record any recipe changes before dependent strength tests.

Data expansion is authorized. After the initial fit and strength results, check
training/dev gaps and held-out learning curves. If data limits either large
model, expand the disjoint expert corpus and rerun matched controls before an
architecture conclusion. Do not treat correlated positions as independent
games. Include corpus game counts and policy diversity, not only row counts.

First-residual-run update: the dev score stops improving by epoch 5 while train
loss keeps falling. Add a small-cold control with the same architecture and
3e-4 learning rate as the new networks. Reset all parameters and normalization
statistics; retain the warm E81 control. This separates capacity from the large
pretraining advantage of E81. Keep the failed initial residual run.

Data-scale follow-up: collect 20,000 extra unchanged AlphaZero800 expert training
games at master 5110000000, 200-game shards and eight workers while initial GPU
training continues. Replay every transition. Keep the existing disjoint dev
split. Add4,000 canonical Gumbel800 training games on separate seeds to keep
the native/canonical ratio near5:1. This gives about 1.7M training positions
from 30,000 games. All model controls get the same expanded rows and targets.
Keep initial models and learning curves. Label timings under shared load.

History implementation: use the exact public unseen-card mask, recovered from
the sampled unknown/deck union during offline preparation and directly from
Observation at inference. Keep this input separate from ground-truth labels.
Feed predicted opponent action probabilities and masked reservation beliefs
back into the policy/value representation through an initially zero projection.
For an initial history study, warmstart the better-fitting new full network;
also run a parent continuation at the same extra epoch budget. Use 12 additional
epochs at AdamW1e-4, with opponent CE weight0.25 and hidden reservation CE
weight0.10. Run a history-only training control and no-history inference
ablation; distinguish inference ablations from causal training controls.
The entity model fits dev data better than the residual model in the initial
12-epoch runs, so it is the provisional history parent. Strength/cost evidence
and expanded-data results can revise this choice before a final claim.

A gather-based entity tokenizer preserves the same fields exactly and may
replace many small device writes after CPU/MPS parity checks. It changes no
model parameter, policy, target or architecture. Record its use in manifests.

Initial history control update: add the state-only auxiliary condition as a
full12-epoch run from the same entity parent at1e-4, with the same targets,
auxiliary weights and data order. All history tokens are zero and masked.
Keep parent continuation, history-only, and full-history/auxiliary conditions.
This distinguishes auxiliary supervision from public-history information.
The state-only descriptor disables history callbacks and history cache keys.
The expanded training driver waits for all these GPU controls to finish.

Expanded comparison update: compare all four base models against E81 on the
same fresh canonical master 5180000000 and native master 5190000000. Use
separate fresh masters for direct entity/residual and entity/cold-small
comparisons. Select the history parent from direct canonical entity/residual
strength if its interval excludes 50%; otherwise select the lower matched
dev score. Do not replace a selected residual parent with the entity model
for implementation convenience. A residual selection requires a history
extension of that architecture before the study can finish.

Run 12 additional expanded-data epochs for the history extension and an
equal-budget parent continuation. Compare history against E81, the continued
parent and same-weight no-history inference. If a direct canonical gain is
supported, run expanded history-only and state-only auxiliary attribution
controls before the final claim. Initial factorial controls remain required
in all cases. Expanded cost measurements and any warranted 20,000-game
confirmation remain separate requirements.

Expanded history encoding update: version 1 records coarse public action
types and revealed card/token changes. It omits the public reservation slot
selected for purchase. Version 2 adds the public action index in feature 15
and the public market/reservation/tier/noble selection in feature 16. Keep
blind card costs, bonus and points absent. This can let the belief head track
slot moves after a purchase. Keep all version-1 trials and controls unchanged.
Regenerate version-2 prefixes in separate files. Canonical replay must match
all original policy/value row bytes and auxiliary labels before acceptance.
Use version-2 descriptors only with version-2 training. Hash all history,
auxiliary and pool inputs in the new training manifest. Expanded parent
continuation remains on the same original state/policy/value rows.

Use fresh canonical 2,000-game seat-paired comparisons for each candidate against
E81, each other, and the small-data control. Fix Gumbel128/depth16 first; run
cost-matched screens when measured cost differs. Use master seeds from
5100000000 onward, never training/dev/old screens. Include no-search policy
screens to distinguish network quality from search. Reserve20,000 confirmation
for a major supported gain or an ambiguous milestone. Measure inference batches,
memory, training time and whole-game cost, including above-four-worker scaling.
Run required local checks and scripts/promote.py. A confidence interval that
crosses50% is inconclusive, not rejection of an architecture family. A failure
at this data/budget does not establish a fundamental capacity limit.

Use the existing pinned offline Torch environment outside the Rust workspace.
If native full-network inference costs too much, build an opt-in tensor-only
batched inference service. It may receive only legal model inputs, never a
GameState, setup seed, chance RNG or private labels. Freeze checkpoint hashes
and service configuration. Record batching and accelerator numerical limits.

## Schedule change: completed expanded controls

Run the completed small, cold small and residual native/canonical E81 screens
while expanded entity training continues. All models, registered common seeds,
2,000-game counts and search budgets stay fixed. Later runners validate and
reuse the completed reports. Preserve the earlier waiting controller plan.
Screen timing has concurrent training load; final cost measurements still wait
for all fits and strength screens. This change uses no expanded strength result.

## Complete expanded direct matrix

Before expanded entity or history strength results exist, add history/base
residual and history/base entity pairs. Run 2,000 fresh paired native
policy-only games (masters 5190080000 and 5190090000) and canonical Gumbel128
games (masters 5180070000 and 5180080000), depth 16, 14/32 workers. These
are direct architecture comparisons; equal-budget parent continuation stays
the causal training-budget control. Run these pairs after any required
attribution and before final cost measurements. Keep all incomplete games.

## Expanded checkpoint export validation

Check every selected expanded base checkpoint against its Torch predictions
on real dev positions. Probe entity output identity across fixed-batch queue
occupancies before its games. Freeze the parity-check executable beside the
native worker and use it for later history and attribution checks. This adds
validation only; model weights, seed ranges and search budgets stay fixed.
The completed early screens and earlier controller plans remain preserved.

## Native architecture milestones

The expanded entity/E81 policy-only screen is a major positive native result.
Confirm a complete entity or residual native/E81 screen whose lower 95% bound
is above 51% on 20,000 fresh paired games. Masters: entity 5250000000, residual
5250100000. If history beats its equal-budget continued parent in native play
with a lower 95% bound above 50%, run causal controls even when its canonical
screen does not support a gain, and confirm that native parent comparison on
20,000 games at master 5250200000. Keep policy-only budgets, depth 16 and 14
workers. These confirmations remain native-profile evidence. Run them after
cost measurements and before canonical confirmations. Native history results
do not exist when this rule is registered. Earlier plans stay archived.
