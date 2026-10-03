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

First one-hot trial, Gumbel128 versus unchanged AlphaZero800:

```sh
local/strength/inference/bin/python benchmarks/strength/native/schedule.py --games 128 --master 17700000000 --workers 8 --iterations 128 --search gumbel --model local/research/sprint48/ready/first/onehot/runtime.bin --output local/research/sprint48/external-00
local/strength/inference/bin/python benchmarks/strength/native/replay.py local/research/sprint48/external-00/games.jsonl --output local/research/sprint48/external-00/replay.json
local/strength/inference/bin/python benchmarks/strength/native/summarize.py local/research/sprint48/external-00/games.jsonl --output local/research/sprint48/external-00/summary.json
```

Use a new master/output for each setting. Policy-only uses `--iterations 0`;
larger search can use `800`, `1600`, `3200`, or more. The existing alternate
uses `--search puct`. Selection remains exploratory. AlphaZero stays fixed.
The scheduler fixes candidate depth16/worlds3/Gumbel-cap16. Expose controls
with metadata before tuning them. `--root-only` does not reduce Entity cost.

For original Entity, export `local/research/sprint48/ready/baseline/model.pt`
on another slot. Declare both bindings to one service or run sequentially.
Do not multiply GPU jobs. Measure complete-game throughput. Invalid/incomplete
play stops and retains partial shards. Resume original blocks with receipts
or report schedule failure; do not drop them and choose replacement seeds.

## 4. Train one chosen branch

The data-reuse branch has an existing command:

```sh
python3 research/entity_baseline/bootstrap.py --native-upstream
local/strength/inference/bin/python research/architecture_pivots/train.py --kind entity --parent local/research/sprint48/ready/first/onehot/runtime.pt --data-scale expanded --epochs 2 --batch 512 --device mps --fast-entities --output local/research/sprint48/refit-01
```

Bootstrap verifies all 408 corpus files once. The trainer uses the existing
one-hot/mixed-value recipe/dev selection and resets AdamW. Stop the owned MPS
inference service before fitting unless a measured overlap test supports it.
Export/check the selected new `model.pt` before played selection.

Native-focused sampling/value calibration needs a trainer change. Learner-state
AlphaZero labels need actor mode in `e95/collect.py`. PCR reuses `rich_selfplay`
and `strategy_train.py`; inspect `--help` and record a new recipe. Do not start
the closed `run_efficiency.py` chain. Preserve profile mapping, public rules
flags, and native noble ordering.

## 5. Freeze and confirm

Save `final-freeze.json` before final games: checkpoint/descriptor/binary hashes,
service/backend, search, AlphaZero pin/checkpoint, count/master, unknown rule,
and conservative 55% lower-bound criterion. Choose 1,000, 2,000, or 4,000 from
measured cost; do not edit the count from outcomes. Final master: **17790000000**.

Use the same schedule/replay/summary commands with frozen settings and fresh
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
required ignored files through the existing chunked workflow. This plan is
ready for execution; preparation establishes no new strength result and
starts no background study.
