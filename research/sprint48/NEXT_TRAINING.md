> Superseded by the AhinLendor mandate. No job was launched from this plan.

# Next training branch: PUCT6400 self-play distillation

## Decision

Run one fresh high-search self-play fit from the confirmed first-onehot
checkpoint. Collect **128 training games and 32 development games** with
PUCT6400, depth64, and the same saved parent. Train the existing onehot Entity
arm for four epochs. Keep the current checkpoint and AlphaZero unchanged.
Do not use the running or completed AZ6400 match result to decide whether to
collect, fit, or select this branch. Start only when the owner confirms the
current heavy jobs have released the required CPU and MPS resources.

This tests whether the confirmed policy improves from its own deeper search
targets on new setups. It is a training hypothesis, not a strength claim. The
collector is canonical Rust self-play. It does not reproduce native
chance-universe sampling or dynamic FPU. The new evaluation must use a fresh,
declared native schedule if the trained weights are to support any strength
claim.

## Fixed identities and data

- Parent checkpoint: `local/research/sprint48/ready/first/onehot/runtime.pt`,
  SHA256 `ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
- Collector source: `crates/splendor-arena/examples/rich_selfplay.rs`,
  SHA256 `719b7c7b2532ba2f7bbd3fd2b2c579916b62c4cbc60020eb43b8fc0ab99475b7`.
- Existing collector executable: `target/release/examples/rich_selfplay`,
  SHA256 `8be8713d3d6c4ed377084db8e5dff6d86fcfc74efdb7dd9fa384fb2e69254967`.
  It accepts the 94-byte transferred parent descriptor at
  `local/research/sprint48/external-07/service/13/model.bin`; that descriptor
  export receipt binds the parent checkpoint hash above. Before use, verify
  the executable against a successful build receipt for this exact source.
  If no such receipt exists, rebuild this example after the current search
  job ends, then record the new binary hash. Do not build into a live target.
- Row schema: `canonical-rich-root-v1`, 2,600 bytes per row. `rich_selfplay`
  writes `rows.bin`, `histories.jsonl`, and `complete.json`; it replays each
  game and records terminal outcomes. `data.py` validates rows and writes
  525-float `inputs.bin` plus a location-bound `data.json` receipt.
- Replay corpus: restore only the verified first-generation core archive,
  manifest SHA256
  `c413a533ce69648d5f69994abd0f8458c8f70f33ae2a12b72b351bdd1f7f9399`.
  Use `first/train` as the replay group. Do not train on confirmation games,
  the current AZ6400 games, DAgger labels, or the incompatible 2,232-byte
  expanded-corpus rows.
- Trainer source: `research/training_strategy/strategy_train.py`. Use `--arm
  onehot`, the same parent, four epochs, batch512, and MPS. It applies the
  established mixed terminal/root value target and selects the epoch by
  `visit CE + 4 * terminal Brier`. Keep all epoch checkpoints and metrics.

## Seeds and overlap gate

Proposed unused setup/policy seeds are train `17713000000` / `17713100000`
and dev `17723000000` / `17723100000`. The collector derives each setup as
`Rng(seed + game_index).next_u64()` and derives encoder/curriculum streams
from each policy seed. These values are proposals, not an overlap proof.
Before any seed is consumed, calculate all 160 setup IDs, check full and
low-32-bit IDs against `ANCESTRY_SETUP_IDS.json`, the current campaign
exclusion set, and all active/retained records. Check train/dev disjointness.
If any check fails, stop and reserve new values before collection. Do not use
either final master `17790000000` or canonical master `17791000000`.

## Exact commands

The output directories must be new. Run from the repository root after the
overlap gate and binary identity check. Use the pinned Python environment for
data preparation and training.

```sh
target/release/examples/rich_selfplay \
  --model local/research/sprint48/external-07/service/13/model.bin \
  --output local/research/sprint48/next-training/train \
  --games 128 --seed 17713000000 --policy-seed 17713100000 \
  --iterations 6400 --depth 64 --threads 32 --full-probability 1.0

target/release/examples/rich_selfplay \
  --model local/research/sprint48/external-07/service/13/model.bin \
  --output local/research/sprint48/next-training/dev \
  --games 32 --seed 17723000000 --policy-seed 17723100000 \
  --iterations 6400 --depth 64 --threads 32 --full-probability 1.0

local/strength/inference/bin/python research/training_strategy/data.py \
  local/research/sprint48/next-training/train
local/strength/inference/bin/python research/training_strategy/data.py \
  local/research/sprint48/next-training/dev

python3 research/training_strategy/archive_results.py restore \
  --archive research/training_strategy/artifacts/core \
  --output local/research/sprint48/next-training/replay \
  --manifest-sha256 c413a533ce69648d5f69994abd0f8458c8f70f33ae2a12b72b351bdd1f7f9399
local/strength/inference/bin/python research/training_strategy/data.py \
  local/research/sprint48/next-training/replay/first/train

local/strength/inference/bin/python research/training_strategy/strategy_train.py \
  --arm onehot \
  --parent local/research/sprint48/ready/first/onehot/runtime.pt \
  --train local/research/sprint48/next-training/replay/first/train \
  --train local/research/sprint48/next-training/train \
  --dev local/research/sprint48/next-training/dev \
  --output local/research/sprint48/next-training/fit \
  --epochs 4 --batch 512 --epoch-rows 32768 --seed 800000061 --device mps
```

`epoch-rows 32768` fixes 16,384 sampled rows from each training group per
epoch. The trainer samples with replacement when a group has fewer eligible
rows. It checks train/dev setup disjointness and replay-generation disjointness.
Preserve the selected `runtime.pt`, all four `epoch-N.pt` files, `model.pt`,
`manifest.json`, `complete.json`, collector receipts/logs, data receipts, and
all source and binary hashes. Do not select by a game outcome or change the
training budget after seeing dev or match metrics.

## Time and unresolved setup

The prior pilot measured 310 seconds for 64 PUCT256 games at 32 workers.
Linear scaling to PUCT6400 estimates about 5.4 hours for these 160 games.
This is a planning estimate only. Reserve up to 8 hours for both collections,
30 minutes for restore/preparation/fitting, and 2 hours for a fresh 128-game
native screen if time permits. Stop this branch at 10.5 hours maximum and by
the original deadline, 2026-10-05 19:35:52 UTC. Do not start it if the owner
cannot preserve that budget.

The current `rich_selfplay` command has no timeout or resumable output. It
renames `.partial` files only after all requested games finish. Therefore the
10.5-hour limit is not enforced by the listed commands alone. Before launch,
the owner must supervise the fixed commands, retain logs and PIDs, and ensure
the first collection completes before starting the 32-game development
collection. If the hard deadline is reached mid-collection, keep the partial
files and failure evidence; do not fit incomplete data. No single unattended
driver currently binds these two collections, fit, and optional screen.

The established `run_external.py` is not an evaluation entry point for this
branch: its original exploratory trial allowance is consumed, and this fit is
outside that driver's registered list. Any native screen needs a new isolated
preflight, fresh audited master, and separate output. Do not alter the
confirmed final result or its frozen records.
