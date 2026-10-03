# Playing-strength research

Current work: [STRATEGY.md](../STRATEGY.md) and [the sprint runbook](sprint48/README.md).
Start from confirmed Entity in `STRENGTH_CHAMPION.json` and the saved one-hot
candidate. `CHAMPION.json` is the standalone/demo pointer;
`EFFICIENCY_CHAMPION.json` states its cost scope. Text below records historical
methods/results. Fixed game counts, cost gates, and old lineage are not the
current mandate.

Start revision: `4448c19`. The original `search` policy remains available.
`search128` and `search512` freeze its depth-eight, width-six, Strong-rollout,
Engine-leaf configuration at their named simulation count. `learned128` freezes
the E24 learned-cycle control at 128 simulations. Candidate `--iterations` and
`--depth` do not change these controls.

## Evidence and status

- E23: 32-feature logistic leaf. Strong outcome training. Large internal gain,
  but 19/2,000 development games capped. Not promoted.
- E24: same checkpoint plus observation-history cycle escape. Fresh confirmation
  earned 79.30% conditional credit against Search128; 19,999/20,000 complete.
  Conservative 95% interval [78.33%,80.27%] includes the missing outcome. The
  existing strict promotion gate rejected the one incomplete game. Its decision
  remains intact. This is the current stronger research control.
- E25: 79,044-parameter residual policy/value network and observation-keyed PUCT.
  Outcome-only value learning and one-action policy distillation failed the first
  playing screen. The checkpoint and ablations are preserved.
- E26: enhanced features, residual correction to the logistic value, and teacher
  root-value / soft-policy targets with PUCT and eight-turn heuristic rollouts.
  Passed the strict 20,000-game confirmation against learned128: all complete,
  57.725% credit, 95% interval [56.59%,58.86%]. This is a fixed-simulation gain;
  equal-compute and external checks remain separate.
- E27: independent AlphaZero teacher data and mixed-replay fine-tuning. Lower
  development prediction error did not produce stronger play: 38.75% credit
  against E26 in 200 complete games. Rejected; all evidence retained.

See `research/REPORT.md` for the current results and limitations.
See `EXPERIMENTS.md` for hypotheses recorded before implementation and seed
reservations. Per-experiment folders contain raw reports, checkpoints, training
metrics, manifests, inference parity results, logs and failure evidence.

## Models and algorithms

E25 encodes 290 float32 inputs: relative player resources/progress, reservation
slots with opponent blind IDs masked, market card descriptors, bank, deck sizes,
player count, current-player flag, final-round flag and available nobles.
E26 appends E23's 32 relative progress and affordability features. Both use a
128-unit ReLU stem, a two-layer residual block, a 67-logit policy head and a
scalar value head. E26 adds the E23 logit to the learned value correction.
Main action IDs encode distinct-color takes (0–31), double takes (32–36), visible
reservations (37–48), blind reservations (49–51), visible buys (52–63), and reserved
buys (64–66). Legal masks exclude impossible IDs.

Native inference uses Rust float32 dense layers. PyTorch is used only in the
isolated training environment. Binary weights are included in the source
fingerprint. No inference dependency or allocation was added to splendor-core.

PUCT shares nodes within one real decision, keyed by the exact actor observation
with only the turn counter removed for E25–E29. Transfer models retain the
turn counter because it is a network input. The default samples a fresh hidden world each
simulation. It does not retain the tree across real decisions. Q values belong
to the actor at each node; terminal shared wins retain fractional credit.
Unfinished simulations use a heuristic value, never a declared game outcome.
Payments, returns and noble choices use the existing heuristic. All canonical
legal choices remain in the core. Real repeated main positions can restrict
search to legal purchases, as in E24. The neural models are two-player models;
the tree agent uses Strong for other player counts, not an untested neural claim.

## Reproduction

The Python environment used PyTorch 2.5.1 and NumPy 1.26.4 with Apple MPS.
Training seeds and dependency versions are recorded in model manifests. MPS
bitwise reproducibility is not guaranteed. E23 training uses NumPy 2.4.3.

```
cargo build --release --locked --example neural_data --example neural_data_v2
# E25 independent setup and policy streams:
target/release/examples/neural_data 12000 250000000 950000007 128 learned-cycle local/research/neural-train.bin
target/release/examples/neural_data 2000 260000000 960000007 128 learned-cycle local/research/neural-dev.bin
python research/train_neural.py local/research/neural-train.bin local/research/neural-dev.bin research/e25/model --epochs 20
# E26 uses fresh setup streams and teacher search targets:
target/release/examples/neural_data_v2 12000 280000000 980000007 128 learned-cycle local/research/neural-v2-train.bin
target/release/examples/neural_data_v2 2000 290000000 990000007 128 learned-cycle local/research/neural-v2-dev.bin
python research/train_neural_v2.py local/research/neural-v2-train.bin local/research/neural-v2-dev.bin research/e26/model --epochs 30
```

The large raw training files stay under ignored `local/research/`; their hashes
are in manifests. They have not been deleted. Binary schemas are recorded in
data-generation manifests. Every setup stays within one split. Setup IDs are
used only for grouping and leak checks, never as model features. E25 masks
missing outcome labels. E26 can use an observation-only teacher target without
an outcome; it never calls that target an actual game result.

Development may proceed with incomplete games under the user-approved rule in
EXPERIMENTS.md. Retain all requested outcomes and their conservative bounds.
Final confirmation remains separate from training and development. No claim of
best-in-class or SOTA performance has been established.

## Additional research controls

`search-budget` freezes the original depth-eight, width-six Strong/Engine
algorithm while accepting the caller's iteration ceiling and time budget.
It supports matched search-loop time tests without changing `search128`.
`neural-persistent` retains exact observation-matched nodes between decisions
(up to 32,768 at the decision boundary); it failed the first E29 screen and
is not selected. `neural-expert` uses the rejected E27 fine-tuned checkpoint.

E28 uses the optional final `depth` argument of `neural_data_v2`:

```
local/research/expert-target/release/examples/neural_data_v2 6000 340000000 1040000007 256 neural-rollout local/research/iteration-train.bin 16
local/research/expert-target/release/examples/neural_data_v2 1000 350000000 1050000007 256 neural-rollout local/research/iteration-dev.bin 16
local/strength/inference/bin/python research/train_expert.py local/research/iteration-train.bin local/research/iteration-dev.bin research/e28/model --epochs 30 --replay local/research/neural-v2-train.bin --warmstart research/e26/model/model.pt
```

Despite its historical filename, `train_expert.py` accepts normalized policy
distributions and finite teacher values from native search as well as external
expert data. Missing outcomes are masked. It samples equal counts from new and
replay datasets. See manifests for data hashes and the selected checkpoint.

## Native model transfer

E30 exports the exact pretrained version-80 upstream checkpoint (SHA256 in its
manifest) into native float32 inference. The network uses three inverted
residual blocks, channel and seven-feature mixing, squeeze/excitation, and
separate policy/value heads. Architecture and pretrained model attribution are
retained in `research/e30/UPSTREAM-LICENSE` and the model directory license.
This is transfer of an existing model, not a newly trained original network.

The runtime input is a 56-by-7 board encoded from Observation and a sampled
hidden world. It never reads the true future deck. Card-to-deck-group mappings
are verified by all card costs, bonus and points; group order is not assumed
to equal bonus-color order. Only native main-action logits map into the existing
67-action space, and the core legal mask controls final choices. Payments,
returns and noble choices remain explicit legal core decisions. At turn 124
and later, transferred agents use Strong for real choices and the E23 logistic
value in search; no native turn-cap outcome is introduced.

`transfer-policy`, `transfer`, and `transfer-rollout` are E30 ablations.
`transfer-native` and `transfer-native-rollout` use E31's source-informed
exploration coefficient 0.4, first-play reduction 0.02965 and no uniform prior
mixture. These remain experimental. Exact encoding and inference checks are
in `transfer_inputs`, `check_transfer_inputs.py`, and `transfer_parity`.

`transfer-dynamic` updates the first-play estimate from returned values; its
first screen showed no benefit. `transfer-pool3` samples three observation-derived
worlds per real decision and cycles through them; its fresh 20,000-game test confirms a research gain while retaining three
blocked outcomes and the strict rejection.
Neither variant reads the true setup seed or future deck. E35 reduced native
inference cost by 2.34x with exact saved-output and playing-record equality.


## Self-improvement loop

`flywheel.py` now runs collection, PyTorch training, native export and parity,
then the paired arena gate. It uses the transferred model only as its initial
teacher. Later teachers are selected trained checkpoints. The default run measures one cycle with 5,000 training games and separate
development and gate ranges. Assess strength gain and total wall time
before choosing the next corpus size or teacher budget. Earlier training shards
can provide replay when an explicit multi-cycle schedule is justified.

Run from the repository root with the isolated pinned Torch environment:

```sh
local/strength/inference/bin/python research/flywheel.py \
  --output local/research/flywheel-next --cycles 1 --games 5000 \
  --dev-games 1000 --iterations 128 --teacher-iterations 800 --epochs 10 --threads 14 \
  --teacher-model research/e56/model/model.bin \
  --teacher-checkpoint research/e56/model/model.pt
```

The command starts native Rust workers. Training reads immutable memory-mapped
shards in small batches; it does not put the full corpus on the GPU. The native
architecture and input encoding match version 80 for bootstrap weight reuse.
All Main positions below turn 124 are recorded. Root visits give policy labels;
root selected-edge means and actual terminal credit give value labels. First-six-
turn visit sampling provides opening diversity. Feature encoding uses a separate
RNG and the actor Observation only. Incomplete outcomes are NaN and masked.
The 2,232-byte little-endian row layout is in each shard manifest.

`best.json` identifies the current immutable native checkpoint and its SHA256.
`plan.json` fixes scripts/settings/seed ranges. Stage logs, receipts and events
record data/model hashes, source IDs, work counters and times. Re-run the same
command to resume completed stages. Interrupted stage artifacts are retained as
numbered attempts. Changed scripts/settings require a new run directory.
A completed miniature two-cycle check verifies the wiring, not playing strength.

For direct native evaluation, set `SPLENDOR_BEST_MODEL` and
`SPLENDOR_CANDIDATE_MODEL` to immutable exported `.bin` files and use
`flywheel-best` / `flywheel-candidate`. Files load once per process, outside search;
no Rust rebuild is needed for a new checkpoint. The loop uses `scripts/promote.py`
without changing its strict decisions. The strict rule stays the default. For a registered exploratory campaign,
`--selection-rule provisional` keeps its initial champion fixed and advances
a separate lineage only when requested-credit point bounds exceed50.5%.
This is not a confidence claim. Assess a frozen endpoint against the fixed
champion at a separate milestone before updating `research/CHAMPION.json`.
Missing outcomes receive no wins; strict decisions and intervals remain saved.


`--teacher-iterations` controls collection independently from `--iterations`,
which controls arena evaluation. `--teacher-model` and `--teacher-checkpoint`
select a trained incumbent for a new measured cycle. Runtime/checkpoint hashes
are checked before use. Use `assess_cycle.py CYCLE --output assessment.json`
to report games/positions per complete wall-clock, stage costs, bounded win
credit and conditional relative Elo gain per hour. A screen is provisional.
Do not interpret one accepted cycle as proof that repeated learning compounds.
The earlier automatic 20k/75k follow-on collection was stopped under the new
measurement-first objective. Its plan and existing data remain preserved.


Cycle 0 is confirmed and selected for research, with its strict missing-game
rejection retained. Start a new measured iteration with its `.bin` and `.pt`
files via `--teacher-model` and `--teacher-checkpoint`. Use
`--dev-teacher-iterations 128` to keep development cost/size fixed while changing
training teacher budget. E42 compares 256/800 teaching from the same accepted
checkpoint and identical 128-simulation evaluation. Its seed ranges and 5,000-
game confirmation sizes are fixed before collection in `EXPERIMENTS.md`.

Normal learning cycles use a fixed 2,000-game paired gate (`--confirm 0`, the
driver default). An inconclusive gate retains the incumbent and continues. Use
`--confirm 20000` only for milestone models, external claims, or ambiguous
results. Do not stop early by repeatedly checking fixed 95% intervals.

The native loader also accepts `SPGATED1` gated residual checkpoints. Use
`--architecture gated --selection teacher --learning-rate 0.001` with the
learning driver to train this student. The first cross-architecture cycle
starts from scratch. Later accepted gated checkpoints warm start normally.
Teacher collection still uses the current model. Core rules, Observation
encoding, policy action mapping, and tree search are shared with the bootstrap.

For the semantic bit-input student, also use `--bitplanes`. Optional
`--distill-incumbent --selection distillation` retains teacher predictions
alongside search/outcome labels. Checkpoints record the architecture, source
hashes and teacher checkpoint hash. E45 and E46 both failed their fresh strength
gates; their speed gains do not authorize a model promotion.

`--trunk-blocks 3` adds two identity-initialized residual blocks to the
bootstrap architecture. Later warm starts preserve their stored depth when
this option is omitted. Native `SPMOBIL1` exports record depth in the header.
E47 is trained and passes native parity; its fresh strength gate is pending.
Use [HANDOFF.md](HANDOFF.md) for the current checkpoint and next command.

Offline target controls: `--policy-only` freezes the bootstrap trunk and value
head, including running statistics. `--greedy-targets` keeps soft root visits
for turns0–5, then shares target mass across maximal-visit actions. Both options
work in the trainer and cycle driver. Saved datasets remain unchanged. E49–E51
record the hypotheses and arena decisions; these options do not establish a
strength gain by themselves.

`--architecture split-bootstrap` trains independent policy features with a
frozen bootstrap critic. It accepts a bootstrap or split checkpoint. Both
encoders receive the same392 observation-derived floats. Native `SPDUAL01`
uses an8-byte magic, two little-endian u32 payload lengths, then policy and
critic bootstrap payloads. Each payload gets the existing depth/finite/size
checks. Native inference evaluates the policy path and critic path separately;
it does not evaluate unused heads. E52 records exact critic bytes, initial
function identity, checkpoint reload, native parity and cost. Extra inference
cost needs playing evidence; the E52 screen did not establish a gain.

`--selection-rule provisional` permits an exploratory lineage after one fixed
2,000-game screen when requested-schedule worst-case point credit exceeds50.5%.
It leaves the fixed `champion.json` unchanged and preserves strict gate outputs
and95% intervals. This point rule does not confirm improvement. Use a reserved
independent champion assessment for claims and promotion. No naive optional
stopping or invented missing outcomes is permitted.

`--encoding-views 8` captures seven extra inputs only for opponent-blind rows,
with a separate RNG. The original data and trajectories stay exact. Sidecars
use a u64 primary-row index followed by7x392 float32 inputs. `--sample-encoding-views` samples one of the eight inputs per training visit, keeping masks and
labels unchanged; an independent augmentation RNG preserves the row order.
Dataset/sidecar hashes, source code hashes and actual blind frequency are saved.

For a registered target-aggregation experiment, `--teacher-replicates 2`
(or4/8) averages independent teacher searches on each recorded Observation.
The first teacher still selects all trajectory and opening actions. Additional
label simulations and inference calls are reported separately. The default
is1; its training bytes match the original collector exactly. This mode has
passed trajectory/input/label-mask checks, but has no strength result yet.

The `residual` architecture keeps a learned bootstrap base fixed and trains a
512-input RMSNorm/SwiGLU correction branch. It requires a learned checkpoint.
Use `--architecture residual --teacher-model research/e59/model/model.bin
--teacher-checkpoint research/e59/model/model.pt` with the flywheel runner.
The correction heads start at zero. The trainer checks that all base weights
and normalization buffers stay unchanged and exports an `SPRESID1` native file.
Existing residual checkpoints can continue training. PyTorch stays offline.

Use `endpoint_cost --budget-sweep` with `SPLENDOR_BEST_MODEL` and
`SPLENDOR_CANDIDATE_MODEL` to measure candidate budgets from 8 to 128 in steps
of eight against a fixed 128-simulation baseline. Three runs alternate order
on the same 568 observations. Select the cost budget before arena outcomes.
The sweep is a host-specific cost measurement, not a playing-strength result.

Use `--actor-iterations 128 --teacher-iterations 800` to train on states visited
by the cheaper student. Only actor policy controls moves and opening sampling.
Independent teacher agents query the same actor observations for labels. The
native collector uses `--iterations 800 --actor-iterations 128`. Its manifest
separates actor and label work. Omit the actor flag to retain teacher self-play.

Public reservation context: `--public-context` appends seven Observation fields
and exports SPINFO57. The collector writes a `.context.bin` sidecar (f32[7] per
unchanged 2232-byte training row). The runner records its hash; SPINFO57 teachers
and warm starts enable context automatically. Only full bootstrap students are
supported. Old corpora need exact reconstruction; missing sidecars fail. E70
validates compatibility; E71 retains E68 after a negative matched-data screen.

Provisional Gumbel search: `flywheel-gumbel` loads SPLENDOR_BEST_MODEL and uses
noise0. `flywheel-gumbel-noisy` uses noise1 for teacher exploration. Both use
completed-Q targets instead of visits. Collection supports `--teacher-agent`
and `--actor-agent`; a separate actor name requires `--actor-iterations`.
E73 is a frozen-model screen, not proof of a learned gain or public rank.

Use `--search-agent gumbel` to screen each trained candidate and its parent with
Gumbel; it selects `flywheel-gumbel-candidate` (SPLENDOR_CANDIDATE_MODEL) against
`flywheel-gumbel` (SPLENDOR_BEST_MODEL). An epoch-zero public-input expansion
has the same function and is skipped even when the native header hash differs.

The unchanged AlphaZero native baseline is preserved with all158 artifact hashes and46 lossless archives. See [benchmark integration](../benchmarks/strength/native/INTEGRATION.md). E56 scored23.395% at128 simulations and37.775% at800 under native rules with AlphaZero's information advantage. Use fresh native-profile milestone tests, hashes and replay; do not pool this transfer baseline with canonical results or treat800-search strength as a learned gain. Keep20,000 confirmations outside the2,000-game inner loop.

External target is critical: E92 records current E81 Gumbel128 at 27.325% against unchanged native AlphaZero800. This triggers a supervision/representation pivot. Do not treat internal lineage gains as dominance. E94 proves the public-input external-teacher data interface; new models need fresh native and canonical checks.
