# Execution runbook

Read [STRATEGY.md](../../STRATEGY.md) first. Run from the repository root.
Use new output directories. Record `start_utc`, `deadline_utc`, owned PIDs,
ports, source/binary hashes, and consumed seeds in campaign `run.json`.
[PLAN.json](PLAN.json) contains identities and reserved seed ranges. Do not
use final masters until the candidate and sample size are frozen.
New masters use the 17.7-billion range to avoid old E87/E88 confirmation
masters. A scan of retained JSON/Markdown/Python/Rust records found no prior
use of the chosen base/final masters. Check consumed setup IDs and active jobs
as well; a new master alone is not a split-overlap proof.

## Continued research after the confirmed win

The user requested more work after the AlphaZero800 result was delivered.
[FOLLOWUP.json](FOLLOWUP.json) records the finite follow-up plan under the
original deadline. A 256-game common-budget canonical diagnostic is running.
A separate fixed 1,000-game native test against AlphaZero with 6,400 simulations
is being prepared. The confirmed candidate is unchanged. The stronger-opponent
test changes only AlphaZero's simulation count and keeps the original 800-search
result separate. Its isolated harness preserves the first freeze's source files.
One owner schedules both jobs; the second job starts after the first exits.

## Restore the completed campaign

The campaign started at **2026-10-03 19:35:52 UTC** and completed at
**2026-10-04 13:47:15 UTC**, before its fixed deadline of
**2026-10-05 19:35:52 UTC**. The 1,000-game final confirmation scored
**77.5% win credit** against unchanged AlphaZero800. Its conservative paired
95% interval is **71.43–83.57%**, with no caps or unknown outcomes.

The selected first-onehot runtime SHA256 is
`ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
The final profile used dynamic PUCT6400, depth64, world3/chance3, 64 workers,
MPS FP32 batch32 and master17790000000. Freeze ID:
`feed64ad3e0555699264972c1a086e305e0b7c17e311dfe3560f88e956d97e58`.
All owned driver, service, schedule and sleep-prevention processes stopped.
Replay verified 1,000 games and 55,466 transitions. The independent final
audit passed. See [RESULTS.md](RESULTS.md), [FINAL_DECISION.json](FINAL_DECISION.json)
and [FINAL_DELIVERY.md](FINAL_DELIVERY.md) for results and archive restoration.

Do not repeat completed trials, fits, collection, labels or the final run.
Refit01 improved its declared dev score but scored below the saved first-onehot
checkpoint in the larger native search screen. Branch2 retained epoch0 parent
bytes because both new updates had worse declared dev scores. Both failed
recipes and the pre-freeze launch failure remain archived.

Completed trial07 used the saved firstonehot runtime:

```sh
local/strength/inference/bin/python research/sprint48/run_external.py --checkpoint local/research/sprint48/ready/first/onehot/runtime.pt --output local/research/sprint48/external-07 --master 17707000000 --games 128 --iterations 6400 --workers 64 --search puct --depth 64 --world-pool 3 --chance-universes 3 --dynamic-fpu --binary-directory local/research/sprint48/build-dynamic/release/examples --port 19727 --device mps --batch 32
```

This command records the completed exploratory trial. Its master is consumed;
do not repeat it. The final model is selected, and the 1000-game count and
search settings are registered. A successful final freeze and fresh final
schedule are still required. Preserve failed and unused fits.

## 1. Restore the starting checkpoint

```sh
python3 research/sprint48/prepare.py --attach-assets
local/strength/inference/bin/python research/entity_baseline/check.py
```

Preparation restores only one-hot checkpoints and fit manifests from the
verified committed core archive. It copies the confirmed Entity parent.
Repeat runs check hashes and reject different existing files. `ready.json`
binds paths/identities. No trainer, service, game, or clock starts. No full
corpus is restored. `--attach-assets` links the pinned Python runtime, upstream,
and checked export fixtures. Default source: `/Users/payton.jones/dev/splendorust`;
another host can use `--assets-root PATH` and `--runtime VENV`. Source data
stay read-only.

Inference candidate: `local/research/sprint48/ready/first/onehot/runtime.pt`,
SHA256 `ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
The sibling selected training `model.pt` has SHA256
`192bb6d86a3b920f200d8fbd1561d706b210aa44d308d8582d4da15a9f395625`.
Use the runtime checkpoint for export/serving. Both contain selected weights;
the runtime payload records the architecture.

Generation-two fits are also in the core archive: `second/iterative/runtime.pt`
and `second/frozen/runtime.pt`, hashes in `research/training_strategy/CLOSED.json`.
They have no established adoption advantage. Do not restore all variants.
Use `archive_results.py restore` for a full corpus only when needed, then
rebuild location receipts with `data.py`, as the closed-study handoff says.

## 2. Build and bind the runtime

After Rust changes, finish checks before outcome jobs:

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --release --locked -- -D warnings
cargo test --workspace --release --locked
```

For unchanged Rust, use a current matching successful receipt and build once:

```sh
cargo build --release --locked -p splendor-arena --bin splendor --example native_policy_worker --example strength_worker --example transfer_parity --example rich_selfplay
```

Tests/builds can replace example executables. Finish them before a run, save
binary hashes/copies, and do not build into an active target directory.
Native scripts use `target/release/examples`. An explicit frozen-binary path
is a useful small runner extension if concurrent code work is needed.

Export for a **new owned port**, then start the service:

```sh
local/strength/inference/bin/python research/architecture_pivots/export.py local/research/sprint48/ready/first/onehot/runtime.pt --port 19720 --slot 13
local/strength/inference/bin/python research/architecture_pivots/service.py --model 13:local/research/sprint48/ready/first/onehot/runtime.pt --port 19720 --device mps --batch 32 --delay-ms 1 --fast-entities
```

Keep that service in an owned terminal/session. Save PID, command, log,
checkpoint SHA, device, batch shape, and source hashes. Do not reuse another
study's service. `research/training_strategy/runtime.py::Runtime` can manage
this in a new finite driver; the old `run_first.py` is not that driver. Archived
descriptors contain old ports and must be exported again.

In a second process, check the real-position fixture:

```sh
target/release/examples/transfer_parity local/research/sprint48/ready/first/onehot/runtime.bin local/research/sprint48/ready/first/onehot/parity.json real
```

The export receipt binds checkpoint/descriptor. Numerical parity does not prove
cross-device trajectory identity. Keep the final backend fixed.

## 3. Run one external development trial

The finite driver now binds sources, frozen binaries, an owned service,
parity, the paired schedule, replay and both native/cap-sensitive statistics:

```sh
local/strength/inference/bin/python research/sprint48/run_external.py --checkpoint local/research/sprint48/ready/first/onehot/runtime.pt --output local/research/sprint48/external-00 --master 17700000000 --games 128 --workers 8 --iterations 128 --port 19720
```

Trial00 is already consumed. Use the next unused master and a new output.
`RUN.json` and `RESULTS.md` record progress. For the checked updated binaries,
pass `--binary-directory local/research/sprint48/build-dynamic/release/examples`.
This target has checked finite-chance and dynamic-FPU controls.
Use `--depth`, `--world-pool` and `--gumbel-max-considered` to change search
coverage. Copies are made before play and used for every shard. Keep the
original receipt and source snapshots for the pre-change baseline.

First one-hot trial, Gumbel128 versus unchanged AlphaZero800:

```sh
local/strength/inference/bin/python benchmarks/strength/native/schedule.py --games 128 --master 17700000000 --workers 8 --iterations 128 --search gumbel --model local/research/sprint48/ready/first/onehot/runtime.bin --output local/research/sprint48/external-00
local/strength/inference/bin/python benchmarks/strength/native/replay.py local/research/sprint48/external-00/games.jsonl --output local/research/sprint48/external-00/replay.json
local/strength/inference/bin/python benchmarks/strength/native/summarize.py local/research/sprint48/external-00/games.jsonl --output local/research/sprint48/external-00/summary.json
```

Use a new master/output for each setting. Policy-only uses `--iterations 0`;
larger search can use `800`, `1600`, `3200`, or more. The existing alternate
uses `--search puct`. Selection remains exploratory. AlphaZero stays fixed.
The scheduler defaults to candidate depth16/worlds3/Gumbel-cap16; the explicit
controls and accepted-setting handshake now allow other values. Check the
selected worker before using them. `--root-only` does not reduce Entity cost.

For original Entity, export `local/research/sprint48/ready/baseline/model.pt`
on another slot. Declare both bindings to one service or run sequentially.
Do not multiply GPU jobs. Measure complete-game throughput. Invalid/incomplete
play stops and retains partial shards. Resume original blocks with receipts
or report schedule failure; do not drop them and choose replacement seeds.

## 4. Train one chosen branch

The data-reuse branch has an existing command:

```sh
python3 research/entity_baseline/bootstrap.py --native-upstream --runtime local/strength/inference
python3 research/sprint48/run_refit.py
```

Bootstrap verifies all 408 corpus files once. The trainer uses the existing
one-hot/mixed-value recipe/dev selection and resets AdamW. Stop the owned MPS
inference service before fitting unless a measured overlap test supports it.
The finite wrapper owns the process and deadline; its receipt directory is
`refit-01`, and the trainer writes to a new `refit-01/fit` directory. Preserve
the venv interpreter path. Export/check the selected `fit/model.pt` before
played selection. The fit is complete; do not launch it again.

Native-focused sampling/value calibration needs a trainer change. Learner-state
AlphaZero labels now use `learner_data.py` to replay fixed native histories and
label the learner's turns offline. See `DAgger_PREREGISTRATION.md`; the small
CPU pilot passed. The fixed second branch now uses `run_branch2.py` and
`branch2_train.py`; see `DAGGER_BRANCH2_PREREGISTRATION.md`.
Source setups become training data and need fresh later evaluations. PCR reuses `rich_selfplay`
and `strategy_train.py`; inspect `--help` and record a new recipe. Do not start
the closed `run_efficiency.py` chain. Preserve profile mapping, public rules
flags, and native noble ordering.

## 5. Freeze and confirm

The active run has a saved `final-freeze.json` that binds checkpoint,
descriptor and binary hashes, service/backend, search, AlphaZero pin,
count/master, unknown rule and the conservative 55% lower-bound criterion.
Its fixed count is **1000 paired games** and its final master is
**17790000000**. Do not change the profile or count.

Use `run_final.py` for the one global frozen campaign. It copies and binds
inputs, starts the owned service, checks parity, freezes the profile, and runs
the fixed schedule. Pass the selected checkpoint, count, search settings,
copied binary directory and every relevant corpus registry. For a branch2
candidate, use its generated four-group registry. `freeze.py check` can audit
a proposal without consuming the final campaign. Active data/label/training
jobs must end and have retained receipts first. Historical ancestry exclusions
are hash-bound. Do not launch an ordinary development driver on final seeds.

Use the same replay/summary checks with frozen settings and fresh
final output. Controlling field:
`conservative_hoeffding95_missing_envelope[0]`. Require all planned blocks,
replay success, consistent receipts, at most 1% no-action, and no invalid/
decision-limit record. Report native caps and a caps-as-unknown sensitivity
from the same paired blocks. The existing summary counts terminal categories;
add that second bound if needed. Keep all requested games.

Optional canonical diagnostic: serve final and original Entity descriptors,
set `SPLENDOR_CANDIDATE_MODEL` and `SPLENDOR_BEST_MODEL` to those paths, then:

```sh
target/release/splendor compare --agent-a flywheel-gumbel-candidate --agent-b flywheel-gumbel --games 256 --seed 17791000000 --threads 64 --iterations 128 --depth 16 --output local/research/sprint48/final-canonical.json
```

This is a common-budget diagnostic if the external budget is larger. Use
`scripts/promote.py` and its canonical interval for canonical promotion.
Do not delay external proof for this optional comparison.

## Final handoff

Save `RESULTS.md`, weights/recipe/lineage, search/backend, records, replay,
statistics, costs, and failures. Preserve the original archives. Archive
required ignored files through the existing chunked workflow. The campaign is complete. FINAL_DECISION.json and the verified final archive
establish the scoped decisive native result. Keep exploratory results separate.
