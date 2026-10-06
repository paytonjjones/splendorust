# Entity training-strategy study

Status: **first-stage evidence checked; second-generation data audited; fits running.** The full goal remains open.
The label, iterative-learning and efficiency questions must be answered from
fresh canonical games. Do not mark this study complete because its code passes.

Worktree: `/Users/payton.jones/.codex/worktrees/training-strategy/splendorust`.
Branch: `codex/training-strategy`. Baseline: clean commit `7367b05`, exact Entity
hash `cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84`.
The original architecture study and its active controllers are separate.

Read `PREREGISTRATION.md` for the fixed hypotheses, seeds, budgets and selection.
`upstream-audit.json` binds the pinned AlphaZero source, checkpoint, saved
settings and source locations. Its settings support pipeline hypotheses;
they do not prove the full checkpoint training history. The root Q value
used upstream is distinct from this study's extra explored-action Q output.

## Current execution

`run_first.py` owns a local service on port 19620 and the rich collector.
The first study output is `local/research/training-strategy/first`.
The controller log is `research/training_strategy/first-controller.log`.
Read its `progress.json`, command-stage `process.json`, and service `run.json`.
Check those process IDs with `ps` before deciding whether a run is live.
A stale progress file alone is not proof. Do not start duplicate controllers.

For a compact status report that checks process identity and recent service
work, use `python3 research/training_strategy/status.py local/research/training-strategy/first`.
The collector writes each batch only after all 64 games finish. Empty partial
files during that batch do not show a stalled job. Check the live collector
PID and the service request count together. The 4-worker pilot completed all
64 games in 3,148 seconds. `pilot-4-target-audit.json` records an independent
check that each terminal label matches its retained game record. Its search
policies assign 35% mean probability to actions other than the chosen move.
These pilot data are excluded from training and strength evaluation.
Read `COLLECTION_COST.md` for the measured workload comparison, padded batch
cost and shared-host limitations.
The 8-worker pilot completed all 64 games in 1,065 seconds. Its target rows,
packed inputs and ordered histories match the 4-worker bytes exactly.
`pilot-8-target-audit.json` checks its terminal labels against saved outcomes.
The 16-worker pilot completed all 64 games in 550 seconds with the same target,
input and history bytes. Its independent check is `pilot-16-target-audit.json`.
The 32-worker pilot completed all 64 games in 310 seconds. All four worker
counts have identical data and histories. `pilot-32-target-audit.json` checks
the last pilot. The controller passed its scaling checks and started the
registered training corpus. All 2,000 training games completed and replayed
in 8,865.911 seconds. `training-target-audit.json` binds 111,136 retained rows,
111,065 eligible targets and the exact raw/input/history hashes. All terminal
labels match the game records; each eligible row has 256 root visits. There
are no incomplete games. The 71 other rows are excluded from training. The
400-game development collection also completed and passed
`development-target-audit.json`: 22,283 eligible targets, zero incomplete games.
All three matched fits completed, each selecting epoch 1. Their held-out
metrics and checkpoint hashes are in `first-stage-evidence.json`. The completed
onehot-versus-original screen has 2,000 complete games: 56.325% win credit,
95% interval 52.03–60.62%. This supports a gain for this first offline pass;
it does not establish a soft-target, Q, iterative or major strength benefit.
The visits/original screen completed all 2,000 games with 56.05% credit and
95% interval 51.71–60.39%. The visits-Q/original screen completed all 2,000
games with 54.875% credit and interval 50.57–59.18%. Only onehot and visits
pass the registered 51% lower-bound benefit threshold. None reaches the 60%
major-gain point threshold. The direct visits/onehot screen completed all
2,000 games with 49.45% visits credit and interval 45.21–53.69%. It supports
neither a benefit nor a clear regression from visit targets. The Q/visits
screen finished with 49.30–49.35% Q credit and interval 45.02–53.63%. It has
1,999 complete games, one no-action game with unknown outcome, and no capped
games. It cannot support Q adoption or pass strict completion. All five
first-stage records and their model bindings have been checked. The chain's
`first-verified.json` retains full source, fit and target checks; the first
study's `evidence.json` contains its strength and cost summary.

The registered fallback selected visits for the common generation-two
parent. Do not adopt visits from lower held-out loss or this research
selection. Generation two is running in
`local/research/training-strategy/second`, starting with current-model
collection. Its plan fixes parent and teacher hashes, 2,000 new common
setups, independent policy streams, 400 new development games, 50/50 replay
and identical fit budgets. Its five canonical strength screens are pending.

Each command records arguments, model paths, return code and measured seconds.
The raw rows and ordered histories remain on disk. Data receipts verify hashes,
legal/explored masks, Q units and conservation, target entropy and exclusions.
Rust replays every recorded game and checks every actual transition invariant.
Incomplete games retain no outcome. Only finite-outcome, full-search Main rows
can train. Audit seed and decision fields are excluded from the 525 model inputs.

The first controller checks 32 real dev fixtures, collects worker scaling at
4/8/16/32, requires identical rows and ordered histories, collects common
train/dev games, fits all three arms, then runs five fresh 2,000-game screens.
It preserves the baseline and official champion byte for byte. Its receipt
requires frozen source hashes. Do not edit its listed source files during a run.
Do not overwrite partial or failed outputs when recovering a command.

## Commands

From a fresh checkout, restore the exact corpus/runtime paths with:

```sh
python3 research/entity_baseline/bootstrap.py --native-upstream
local/strength/inference/bin/python research/entity_baseline/check.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --release --locked -- -D warnings
cargo test --workspace --release --locked
local/strength/inference/bin/python -m unittest discover -s research/training_strategy -p test_strategy.py -v
local/strength/inference/bin/python -m unittest discover -s research/training_strategy -p test_efficiency.py -v
cargo build --release --locked -p splendor-arena --bin splendor --example rich_selfplay --example transfer_parity
```

Start the first study only in a **new** output directory, with new registered
masters for any repeat. The existing command is:

```sh
local/strength/inference/bin/python -u research/training_strategy/run_first.py --output local/research/training-strategy/first
```

Once the first comparison has completed and its evidence has been checked:

```sh
local/strength/inference/bin/python -u research/training_strategy/run_iterative.py --first local/research/training-strategy/first --output local/research/training-strategy/second
```

This selects the registered label rule, collects a current-model second
generation plus a matched frozen-teacher control, uses 50/50 recent replay
with identical update counts, and evaluates both against each other, the
static first-generation model and the original Entity. It does not promote.
Check its command/data receipts before treating any result as valid.

`EFFICIENCY.md` registers the cap-randomization control before any trained
model or strength result. Run it after the first two studies are checked:

```sh
local/strength/inference/bin/python research/training_strategy/run_efficiency.py --first local/research/training-strategy/first --second local/research/training-strategy/second --output local/research/training-strategy/efficiency
```

It changes only full256/cheap64 caps. It matches generation by useful model
inference calls within 2%, retains every paid chunk, and uses the full control's
parent, development set and fit-update budget. Wall time and padded GPU work
can differ and must be reported. Two excluded pilots measure cost/target yield;
two fresh 2,000-game screens measure PCR versus full generation two and versus
original Entity. Four accounting tests check byte preservation, exclusions,
duplicate setups, cap mismatch and terminal-label mismatch. This controller
has not yet run; a passing accounting test is not evidence of efficiency.
The real-data assembly preflight also split and rejoined the 64-game pilot.
Its rows, inputs and ordered histories kept the original SHA256 hashes.
`efficiency-data-preflight.json` marks the partition times as fixture values,
not new cost measurements. `strategy_summary.py` has a unique module name;
the `summarize.py` command remains a compatibility entry point.

Check terminal label accounting and search-target content for each completed
corpus with the same audit used for the pilot:

```sh
local/strength/inference/bin/python research/training_strategy/audit_targets.py local/research/training-strategy/first/train --output local/research/training-strategy/first/train-target-audit.json
```

## Remaining work

- The label comparison is finished and checked; retain its ambiguous results
  and the Q screen's unknown outcome.
- Execute and check the iterative-versus-frozen second-generation comparison.
- Measure collection/training/inference/search costs and strength per compute.
- Execute and check the registered cap-randomization comparison at matched
  inference-call generation cost. Register any additional exploration, budget
  staging or symmetry test before use. Do not attribute untested components.
- Apply a fresh 20,000-game milestone if the registered major-gain condition holds.
- Keep the external AlphaZero target frozen and clearly separate native evidence.
- Archive reproducible checkpoints, data/record hashes and exact commands, then
  write a supported/negative/ambiguous/untested report and a complete handoff.

Validation so far: 126 release tests, strict workspace Clippy, formatting, and
six Python tests pass. Capture-on/off tests preserve actions, old policy/value
targets and work counts. Parent policy/value outputs are bit-identical before
Q training. Q gradients exclude unvisited actions and reach the shared trunk
after a head update. Removing the Q head preserves runtime policy/value bits.
Numerical device parity is bounded fixture evidence, not global trajectory proof.

## Artifact archive and milestone

The completed first stage has been archived and restored while generation two
runs. The archive output is `local/research/training-strategy/first-archive`;
the verified restore is `local/research/training-strategy/first-restored`.
All 246 archived files match their original bytes. The restored train/dev and
four scaling corpora pass the label checks. Location-dependent data receipts
were rebuilt; their original copies are retained. No first-stage file was
omitted. The manifest SHA256 is
`d5674c8d0857444ff943f0180e41c648a8ed30736b854dfa0d018212fa2aff86`.
`first-archive-manifest.json` and `first-archive-verification.json` retain the
manifest and actual restore evidence. Launch receipts and logs remain in the
local study root. This archive is only the first stage. The final archive must
still include second, efficiency and milestone evidence, costs and final reports.

Generation-two current-model collection has finished: 2,000 complete and
replayed games, zero incomplete games, 111,214 raw rows and 7,934.063 seconds.
`second-iterative-target-audit.json` checks every terminal label against its
retained record and binds the raw/input/history hashes. The matched
frozen-teacher collection finished in 8,682.167 seconds: 1,999 complete games,
one no-action game, no capped games. Its 46 unknown-outcome rows are excluded;
111,241 rows are eligible. The new development corpus has all 400 games complete,
22,192 eligible rows and 1,388.865 seconds at 64 workers. Both passed independent
label audits, in `second-frozen-target-audit.json` and
`second-development-target-audit.json`. The adopted collector's parent exit
code remains unknown in `second/recovery-resource-1/adopted-frozen-data.json`.
The iterative fit is running. No generation-two strength
comparison has finished yet. Shared-host collection time is a cost receipt,
not an isolated speed improvement.

Read `MILESTONE.md` for the fixed endpoint selection and confirmation rule.
It also registers a direct frozen-teacher continuation versus original Entity
comparison, so both second-generation arms have a measured cost reference.
After all three studies finish and their results have been checked:

```sh
local/strength/inference/bin/python research/training_strategy/run_milestone.py --first local/research/training-strategy/first --second local/research/training-strategy/second --efficiency local/research/training-strategy/efficiency --output local/research/training-strategy/milestone
python3 research/training_strategy/archive_results.py pack --study first:local/research/training-strategy/first --study second:local/research/training-strategy/second --study efficiency:local/research/training-strategy/efficiency --output research/training_strategy/artifacts
```

The archive uses gzip chunks with SHA256 checks. Restore into a new directory
with the exact manifest hash from `artifacts/SHA256SUMS`:

```sh
python3 research/training_strategy/archive_results.py restore --archive research/training_strategy/artifacts --output local/research/training-strategy-restored --manifest-sha256 MANIFEST_HASH
```

Restored weight, input and row bytes stay unchanged. Original data receipts
with absolute paths move to `data.original.json`. Run `data.py` on each restored
corpus directory to make receipts for its new paths. Old run commands remain
as provenance; export descriptors on a new free port for new evaluations.
The archive preflight restored the exact 19,143,225-byte Entity checkpoint
and a 100 MiB three-chunk fixture. It also rejected a corrupt gzip chunk.
These are archive checks, not training or strength results.

## Interrupted screen recovery

The original controller stopped during `screen-visits`; its process and unified
process handle were absent. The completed collections, three fits and onehot
screen passed fresh checks. The arena executable still matched the completed
onehot screen byte for byte. All frozen study sources and weights matched.
The current collector executable has different bytes from the collection plan;
collection is already complete, so recovery does not use that executable. Both
identities remain in the recovery receipt. Its cause has not been isolated.

Recovery starts from the saved checkpoints with the same four remaining
comparisons, masters and search budgets. The interrupted visits files are
retained under `first/recovery-1/interrupted` and excluded from final counts.
The old service directory is preserved. The new owned service and recovery
plan are under `first/recovery-1`; its log is `first/recovery-controller.log`.

The running recovery command is:

```sh
local/strength/inference/bin/python -u research/training_strategy/resume_first.py --first local/research/training-strategy/first --recovery local/research/training-strategy/first/recovery-1
```

Do not start this command while its process is live. A later recovery needs
a new recovery directory. `--check-only` validates the retained datasets,
completed stages, weights and sources without moving interrupted files.

The first recovery also stopped without a terminal receipt. Recovery 2 was
started after its process IDs were confirmed absent and all saved evidence
passed the preflight again. It uses `first/recovery-2`, preserves the prior
interrupted files and writes `first/recovery-2-controller.log`. The launch
receipt `first/recovery-2-launch.json` binds its detached process and command.
This process uses a separate OS session to continue across chat updates.
The interruption cause is not established. Include interrupted work in cost
accounting but exclude it from final strength counts. `RESULTS.md` is the
provisional results draft; the full study is still incomplete.

## Automatic stage continuation

The user removed the chat follow-up on 2026-10-03 because it sent too many
messages and used tokens. The `continue-entity-training-study` automation is
deleted, and no babysitter helper for this thread is live. Do not create a new
chat follow-up without a new user request. The detached experiment chain
continues; this removal does not stop the experiments or complete the goal.

`continue_study.py` waits for the live first controller to finish. It then
checks all five raw canonical reports, source/weight/build hashes, fit exits,
search settings and independent target audits before it starts generation two.
It applies the same checks before efficiency and the registered milestone.
It uses the existing experiment controllers, seeds and budgets. It never
repeats an existing stage. A stopped process without a completion receipt or
a failed check stops the chain and writes a failure receipt.

The current detached chain runs under `local/research/training-strategy/chain-2`;
its launch receipt is `local/research/training-strategy/chain-2-launch.json`
and its log is `local/research/training-strategy/chain-2-controller.log`.
Check its PID and progress before starting any later stage manually. The
former chat follow-up is deleted at the user's request.
The original chain-1 and second-stage controller were deliberately stopped
after the user's resource request. The original frozen collector is still
running, adopted by `run_iterative_resource.py` under
`second/recovery-resource-1`. Its log and launch receipt are
`second-resource-controller.log` and `second-resource-launch.json` in the
local study root. `second/resource-handoff.json` records the original process
identities, progress and stop reason; `resource-original-chain.bin` preserves
the old chain source bytes. Do not classify this planned handoff as a crash.

Read `RESOURCE_AMENDMENT.md`. The 64-worker pilots have exact collection bytes
and exact ordered arena records. Shared-host collection throughput improved
1.272 times, arena throughput 1.480 times. Development and future evaluation
use 64 workers with the same fixed 32-row GPU arithmetic. The current-model
and frozen-teacher generation data keep 32 workers, as does PCR generation,
so full/PCR collection costs retain the same worker configuration. No game,
search budget, seed, fit setting or selection rule is changed. Pilot records
and logs are retained under `second/recovery-resource-1/resource-pilots`;
`resource-scaling-evidence.json` keeps the result and hashes. All 17 Python
tests pass. The current chain has checked the completed first stage again.
The chain does not mark the full goal complete. Final cost accounting,
archive/restore verification, the training recommendation and final handoff
remain required after its registered experiments finish.

Read `ARCHIVE.md` for final packaging and cost checks. The archive retains all
regular files, including profile text and interrupted partial bytes. Its optional
`--provenance label:directory` input retains root launch receipts, chain logs and
reports without asserting experiment completion. All 21 Python checks pass.
Final packing and restore verification on the remaining actual data are pending.
The provisional cost inventory is `local/research/training-strategy/cost-inventory-provisional.json`.
`collect_costs.py` counts copied command receipts once, keeps missing exits unknown
and reports service counters separately. It does not close final costs. Four
receipt-accounting tests pass; all 25 Python checks pass.

The frozen-teacher collection has one observed no-action game, game 1533.
All 46 outcome labels are NaN and zero rows are eligible. Preserve its record,
unknown outcome and generation cost; do not replace it. The registered corpus
policy permits incomplete games with excluded labels. Strength screens still
require strict completion for a supported benefit. The partial observation is
`second-frozen-incomplete-observation.json`; `second-frozen-target-audit.json`
now verifies the completed corpus and its excluded rows.

For a fresh chain output after a checked interruption, the command is:

```sh
local/strength/inference/bin/python -u research/training_strategy/continue_study.py --root local/research/training-strategy --output local/research/training-strategy/chain-2 --eval-threads 64
```

Use a new chain directory for a later recovery. Preserve the old chain's
receipts. Do not restart a failed experiment through this command; recover
that experiment's unfinished work first. Existing completed stages are
checked again; existing live stages are left running.
