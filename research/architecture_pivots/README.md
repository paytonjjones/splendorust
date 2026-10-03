# Architecture pivot experiments

Read [REPORT.md](REPORT.md) for results and limits, [PREREGISTRATION.md](PREREGISTRATION.md)
for hypotheses and budgets, and [STATUS.json](STATUS.json) for pending work.
All required stages are complete. Read the report before planning more scaling.
`ARTIFACTS.json` binds retained files; `CHECKPOINTS.json` binds committed selected weights.

The Rust core has no ML dependency. Training and the optional local tensor service
use the existing Python runtime at `local/strength/inference/bin/python`. It has
CPython 3.11 and Torch 2.5.1. Expert collection uses the pinned AlphaZero revision
and runtime recorded in the collection receipts. Do not replace the teacher,
datasets, observation profile or noble order during a comparison.

## Data and checkpoints

The initial registry is `local/research/architecture-pivots/data.json`.
The expanded registry is `local/research/architecture-pivots/expanded-data.json`.
Each registry binds source rows, public context and model inputs by SHA256.
Initial and expanded runs use the same held-out setup IDs. Expanded training
contains 1,682,022 rows from 30,000 setups; dev contains 111,572 rows from 2,000
disjoint setups. Rows within a game are not independent samples.

Each trained directory has `manifest.json` and the selected `model.pt`.
The manifest retains every epoch and the selected checkpoint hash. The
interrupted CPU cold-small run remains separate from the completed MPS trial.
Large raw archives, model files and frozen executables remain on disk.
The directory ignore rules keep them out of normal source commits; selected
checkpoint files can be committed explicitly. Commit `0165030` contains all five selected expanded checkpoints and
`CHECKPOINTS.json`. The separate frozen Entity baseline also contains its
selected weights. The final artifact manifest records retained
paths, byte counts and hashes.
Do not remove them when packaging source changes.

History version 1 and version 2 have separate tensors and receipts. Version 2
adds public action and slot coordinates. Blind-draw card identity remains absent.
Auxiliary labels contain simulator truth and are used only by the offline trainer.
The wire service receives public tensors and legally known private-own-card inputs.
Its descriptor fixes the checkpoint hash and history version.

The exact expanded Entity parent is separately committed at
`7367b05ea3a6587bf9c982756027652eeb974990`. The clean worktree at
`/Users/payton.jones/dev/splendorust-entity-baseline` includes the weights,
all Entity source dependencies, checked evidence, and
`research/entity_baseline/HANDOFF.md`. Its checkpoint SHA256 is
`cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84`.
This is the ongoing history experiment's parent. The freeze does not select
a different parent or change the official champion.

## Execution and evidence

The executed order was:

1. `run_expanded.py`: validate expanded rows and fit all four base controls.
2. `run_expanded_early.py`: run the three finished native-model controls while
   the entity model trains, using the registered seeds and budgets.
3. `run_expanded_study.py`: validate and reuse those completed screens; compare
   the entity, select its strongest large-model parent, audit version 2 history,
   fit the history extension and equal-budget parent, and run fresh games.
   The user stopped the expanded Entity continuation after 10 of 12 planned
   epochs. `resume_expanded_history.py` resumes only the existing post-training
   tests, using the saved selected checkpoints and unchanged seeds/budgets.
   Its receipt preserves the original controller plan and marks the early stop.
4. `run_expanded_attribution.py`: run the registered causal controls if required.
5. `run_expanded_cross.py`: finish fresh history/base residual and history/base
   entity comparisons in both profiles.
6. `run_cost_study.py`: measure whole-game worker scaling, calibrate budgets by
   response cost, and measure strength at those fixed estimated budgets.
7. `run_native_confirmations.py`: confirm supported native architecture gains
   on 20,000 fresh games.
8. `run_confirmations.py`: apply the registered milestone rule with disjoint
   screen and confirmation seeds.
9. `refine_cost_study.py`: after both confirmation stages finish, run the
   corrected finer timing grid and fresh native cost screens. Its current
   plan is `cost-refinement-v2/PLAN.json`; retain the failed first attempt.

These controllers finished. Do not rerun them in their existing output directories.
Inspect each controller's plan, progress, log and completion receipt first.
An existing output directory is protected against accidental overwrite. Preserve
its files before any recovery. A completion receipt for one stage does not mean
the research task is complete.

Native comparisons retain JSONL, compressed ordered records, legal/replay checks,
frozen worker hashes, checkpoint hashes and a setup-block confidence interval.
Canonical comparisons use `scripts/promote.py`, retain full ordered reports and
freeze the executed CLI. Incomplete games have no winner. Canonical P2.1 permits up to 1% no-action
games with conservative unknown-outcome bounds; decision-limit games still
reject promotion. Preserve original decisions and separate reassessments.
Native score-cap results do not establish canonical strength.

Refresh the checked result catalog with:

```sh
local/strength/inference/bin/python research/architecture_pivots/result_catalog.py
```

The catalog checks report hashes, game counts and confidence intervals. It keeps
partial fits, failed executions and small pilots separate. It does not rerun games
or establish an architecture result by itself. Timings under concurrent training
or other host activity remain shared-host measurements.

Render the checked comparison figure in a separate plotting environment:

```sh
uv run --with matplotlib==3.11.2 python research/architecture_pivots/plot_results.py
```

This does not change the training runtime. `architecture-figure.json` binds the
figure, plotting code, library version and checked catalog by SHA256.

The selected expanded history checkpoint also has a separate diagnostic at
`expanded-history/auxiliary-diagnostics.json`. It compares full-history and
zero-history auxiliary predictions on the fixed dev set, with train-only
frequency priors and a uniform public-pool/tier prior. Its confidence intervals
bootstrap whole independent setups, not repeated positions. The CPU metrics
must reproduce the saved selected-epoch metrics within 2e-5. It does not select
a different checkpoint or search budget and is not fresh strength evidence.
Reproduce into a new output path:

```sh
local/strength/inference/bin/python research/architecture_pivots/auxiliary_diagnostics.py --output local/research/history-auxiliary-diagnostic.json
```

## Reproduce the selected history recipe

Use `CHECKPOINTS.json` to verify the selected weights. Restore the corpus from
`TRAINING_CORPUS.json` and the frozen Entity handoff. The history manifest also
binds every version 2 public-prefix tensor, auxiliary label file and public-pool
file by SHA256. These caches remain under
`local/research/architecture-pivots/`; they are required for training, not for
model loading or live inference. Do not replace version 2 caches with version 1.

Train into a new output directory:

```sh
local/strength/inference/bin/python research/architecture_pivots/train_v2.py --kind history --parent research/architecture_pivots/expanded-entity/model.pt --output local/research/architecture-pivots/new-history-study --data-scale expanded --epochs 12 --batch 512 --device mps --fast-entities
```

This reproduces the tested recipe and fixed training seed. It does not launch a
new study by itself or assert a history benefit. For an independent experiment,
register the changed hypothesis, recipe and fresh strength seeds first.
Export a copy of its selected checkpoint so retained study descriptors stay intact:

```sh
local/strength/inference/bin/python research/architecture_pivots/export.py local/research/architecture-pivots/new-history-study/model.pt --port 19559 --slot 0
local/strength/inference/bin/python research/architecture_pivots/service.py --port 19559 --device mps --batch 32 --delay-ms 1 --fast-entities --model 0:local/research/architecture-pivots/new-history-study/model.pt
```

The service command stays running. Use a free port. For canonical evaluation,
set `SPLENDOR_CANDIDATE_MODEL` to the new `.bin` descriptor and
`SPLENDOR_BEST_MODEL` to the frozen E81 model, then use `scripts/promote.py` with
fresh registered seeds, 32 workers, Gumbel128 and depth 16. The exact standalone
Entity loading/export/evaluation commands remain in its frozen handoff.

## Validation

Rust changes require the pinned locked toolchain, formatting, strict workspace
Clippy and release workspace tests. The Python model tests check gradients,
token encoding, parent initialization and allowed belief support. Runtime probes
check actual dev prefixes, checkpoint identity and fixed-batch occupancy parity.
Direct numerical tolerance is not a claim of identical whole-game trajectories.
All current strength trials are two-player trials. They do not establish strength
in three- or four-player games.
