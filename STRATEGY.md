# Beat pinned AlphaZero within 48 hours

Current mandate: 2026-10-03. Prepared from main
`3c1a65678a41db77aac66e034cbb4b5fa1f7b018`.
This is the active research plan. Start with [the runbook](research/sprint48/README.md)
and [the plan](research/sprint48/PLAN.json). The previous Entity training study
is closed. Reuse its outputs; do not resume its old controller.

## Objective and authority

Produce the strongest public-observation SplendoRust agent that this Mac can
train and test before the deadline. Establish a decisive win against the
unchanged pinned AlphaZero800 agent. Size, latency, FLOPs, simulation count,
search depth, and equal compute are not acceptance limits. Use more compute
if it increases winning strength and leaves time to prove the result.

The immediate target is two-player `alphazero-native-32a27ac-v1`. AlphaZero
keeps source `32a27ac1f85d5de2766cc5f60c2bf04e557f7836`, checkpoint
`6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07`, and
800 simulations. Keep its network, search, temperature schedule, rules,
rewards, and information unchanged. SplendoRust may use more compute.
The benchmark adapts SplendoRust to AlphaZero's native referee. AlphaZero
receives its true private partition; SplendoRust receives public observations
and its own private cards. No future deck order enters either agent.

Success means the fresh final conservative 95% lower win-credit bound exceeds
**55%**, with the candidate and sample size fixed before outcomes. This is a
material margin. A lower bound above 50% but at or below 55% supports a win,
but misses the decisive target. Report a loss or uncertain result as such.
Beating this target does not prove a worldwide rank, canonical-rule dominance,
or strength against expert humans.

This plan replaces fixed 128-search and 2,000/20,000-game requirements for new
work and removes equal-latency vetoes. Keep legal actions, truthful outcomes,
the public-input boundary, replay, and final source/model identity. These
checks protect the result from being false. Run local Rust checks after Rust
changes; reuse their receipts for unchanged binaries. Do not repeat full
checks for each new checkpoint or run setting.

## What the completed work says

| Evidence | Meaning for this campaign |
|---|---|
| Expanded Entity, 4.78M parameters: 60.7225% against E81 in 20,000 complete canonical Gumbel128 games; 95% 59.595–61.850% | Use Entity as the confirmed research strength baseline. Do not repeat this confirmation. |
| Expanded residual: 30.975% against E81; history: 46.275% against its Entity parent in canonical screens | Avoid another generic capacity or history sweep. These recipes failed; all architectures are not disproved. |
| First one-hot Entity update: 56.325% against original Entity in 2,000 complete games; 95% 52.03–60.62% | Start from this saved candidate. Its native AlphaZero strength is unknown. The shared value update is part of its gain. |
| Visits versus one-hot: 49.45%, 95% 45.21–53.69%; action-Q versus visits: 49.30–49.35%, 95% 45.02–53.63%, one unknown | Extra visit/Q machinery has no supported adoption benefit in this recipe. Keep one-hot as the first control. |
| Iterative versus frozen generation two: 50.1953% in 256 games; 95% 33.36–67.03% | The result is uncertain. Sustained self-improvement and equivalence are both unestablished. Reuse saved fits only as exploratory candidates. |
| E81: 26.877% unchanged AlphaZero, 29.445% blinded AlphaZero, 28.378% privileged SplendoRust, each 20,000 games | Hidden information explains only a small part of this measured gap. Do not make belief/history the main task. |
| Five first-stage 2,000-game screens: about 10.7 hours; each fit: about four minutes | Reduce development evaluation. Data generation and search inference dominate the schedule. |
| Entity 64-worker arena pilot: 1.48 times 32-worker throughput, with matching ordered records | Start Entity canonical work at 64 workers. Native AlphaZero CPU workers need a separate small load check. |

Sources: [architecture report](research/architecture_pivots/REPORT.md),
[confirmed decision](research/architecture_pivots/expanded-entity-confirmation/decision.json),
[closed training results](research/training_strategy/RESULTS.md),
[first-stage hashes](research/training_strategy/first-stage-evidence.json),
[fairness report](benchmarks/strength/information-fair/REPORT.md), and
[collection costs](research/training_strategy/COLLECTION_COST.md).
These are conditional results, not transitive win predictions.

Entity already used **1,682,022 positions from 30,000 games**: 25,000 native
AlphaZero800 games and 5,000 canonical expert games. This includes E95's data
and the expansion. Starting again with the 143K E95 model would discard the
demonstrated representation gain. E95 remains useful collector/data code.

## Champion and candidate definitions

[STRENGTH_CHAMPION.json](research/STRENGTH_CHAMPION.json) records confirmed
Entity and its existing confirmation. It is the internal research baseline.
The screened one-hot update is the first challenger.
[EFFICIENCY_CHAMPION.json](research/EFFICIENCY_CHAMPION.json) records E81's
measured response-cost scope. [CHAMPION.json](research/CHAMPION.json) keeps the
current standalone/demo runtime pointer. Entity needs a checkpoint-bound local
tensor service. Replacing that file with a socket descriptor would not produce
a working standalone demo. A later runtime release can update it. This
separation must not block strength selection.

Record model strength at a stated common budget, the maximum-strength agent
profile, and the external AlphaZero result separately. Gumbel128 is a useful
historical control, not a final budget requirement. Do not infer native
strength from a canonical win.

## Work order and elapsed-hour schedule

One Sol agent owns decisions, integration, and the heavy-job queue. It can
task up to five Luna helpers, subject to actual tool slots. Use elapsed time,
including sleep, recovery, builds, audits, and evaluation. Record start and
deadline once; use an earlier user deadline if one exists. A resumed chat
does not get another 48 hours.

| Elapsed hours | Primary work | Required decision |
|---|---|---|
| 0–2 | Restore one-hot; verify runtime, upstream, fixtures, and owned processes. Build once. Start a 128-game external baseline while a helper inspects bottlenecks. | Working native evaluation and measured seconds per game. |
| 2–6 | Compare original Entity and one-hot at useful compute. Begin with policy-only and Gumbel128; try the better checkpoint at 800, then more if affordable. Use at most four initial external trials. | Choose starting model/search. Calculate final-run cost now. |
| 6–20 | Run one training branch below. Improve occupancy or search coverage only when measurements justify it. Evaluate one selected checkpoint, not every epoch. | Retain a candidate that improves external development play; stop a failed branch. |
| 20–30 | Run one further generation or one search change if the first result justifies it. Use remaining exploratory trials. | Choose one final checkpoint, backend, search, and sample size. |
| By 32 | Freeze and start fresh confirmation. Move this cutoff earlier if measured cost requires it. | No selection from final outcomes. |
| 32–46 | Finish confirmation, replay, statistics, and identity checks. Add a modest fresh canonical comparison if time permits. | Supported decisive win, smaller supported win, or explicit failure. |
| 46–48 | Save model, recipe, records, costs, and report. Push checked handoff. | Reproducible endpoint and honest conclusion. |

Ceilings: **6 hours of exploratory evaluation**, **2 new training branches**,
and **2 hours of speculative optimization**. Failed optimization uses that
allowance. These are resource-control defaults; Sol can transfer time when
a measured result justifies it. The final proof reserve is mandatory. Keep
at least 16 hours for final play, checks, and delivery, or more if measured
cost demands it. A training success without final play cannot meet the goal.

Before a large run, estimate `games * measured_seconds_per_game`, add 50% for
startup/tails/load, plus measured replay/check time. Select the strongest
profile whose final run fits the reserve. Latency can constrain what finishes;
it cannot independently veto strength. Do not assume linear search scaling
or copy E81 timing to Entity.

## Track A: make search compute buy wins

Hypothesis: Entity policy/value is stronger, but shallow/narrow search prevents
it from defeating AlphaZero800.

Start with the restored one-hot update and exact original Entity control.
Use fixed **128-game exploratory paired** schedules against unchanged
AlphaZero800. Policy-only is a cheap diagnostic. After the initial comparison,
use the better model at 800 simulations. If wins improve and cost fits, test
1,600, 3,200, 6,400, or more. There is no 800 ceiling. One 256-game development
comparison can resolve a close choice if it changes the next action. Small
samples can discard poor branches; they do not establish small gains.

Do not repeat a broad model-by-budget grid. [PLAN.json](research/sprint48/PLAN.json)
reserves eight external exploratory trials for the whole campaign. Allocate
them to decisions with the largest expected effect. Log selection as
exploratory even when its point estimate is high.

Current Gumbel considers at most **16** prior-ranked legal root actions.
More simulations refine those actions; they do not remove the restriction.
Depth is **16 completed player turns**, with **three sampled worlds**.
The native runner exposes PUCT/Gumbel and iterations; its scheduler does not
expose depth or root candidate settings. Trees are fresh each real decision.
There is no fixed node cap. `--root-only` does **not** give remote Entity a
cheap leaf evaluator: its base path calls the same full model. See
`neural_search.rs::gumbel_root`, `simulate_environment`,
`transfer.rs::infer_base`, and the native worker.

If more simulations plateau, allow one bounded task to expose root cap and
depth through worker reset, runner, schedule, and receipts. Check legality,
exact simulation counts, metadata, and native/canonical paths. Compare
cap16/depth16 with cap32/depth32 at a useful larger budget; keep worlds3
initially. Existing PUCT at the same budget is a lower-effort alternative.
Keep defaults reproducible. Do not copy AlphaZero's exploration constants
into Entity without testing them.

A hybrid Entity-root/E81-leaf agent is a fallback if full Entity cannot afford
a useful final search budget. It needs an explicit two-model evaluator and a
fresh test; `--root-only` alone does not implement it. Time-box that work.
Value bias, depth, and the top-action cap can limit gains; more compute is
a hypothesis, not a guarantee.

## Track B: stronger and more relevant training decisions

Default: one-hot policy targets, root/terminal value learning, Entity warm
start, four-epoch maximum, and saved epochs. Keep the existing recipe as the
control. Visits/Q remain available, but the latest results do not justify
rebuilding them first.

Inspect external losses and native held-out predictions. Choose **one** branch
and write a short hypothesis before fitting:

1. **Reuse data before collecting.** Fine-tune one-hot Entity on the verified
   expanded corpus for 1–2 epochs. The existing trainer supports `--parent`,
   `--data-scale expanded`, and Entity. Test whether the canonical update lost
   native teacher behavior or useful fitting remains. If native errors show
   domain mismatch, add native-focused sampling and native dev selection as
   the declared change. Data already are about 83% native; a large gain is
   not assumed. Keep canonical dev as a regression diagnostic.
2. **Label learner states with AlphaZero800.** If imitation fits but external
   play is poor, add learner-actor mode to the native teacher collector. Run
   candidate trajectories or candidate/teacher mixtures; query the unchanged
   teacher on those states for offline action/root-value labels. Target
   1,000–2,000 fresh training games and 200 dev games, subject to a measured
   6-hour collection ceiling. Mix with a declared replay fraction. Store
   teacher labels separately from actor actions. Privileged teacher state
   supplies labels, never learner inputs. Replay/audit a pilot first. This
   needs code: `e95/collect.py` executes teacher actions, not learner actions.
   Native evaluation logs only public-observation hashes. A learner collector
   must retain/reconstruct the actual public observations and align actor
   actions, teacher labels, chance draws, and terminal outcomes before fitting.
3. **One efficient self-play generation.** If higher-budget candidate search
   is strong, use it as the next teacher. `rich_selfplay` supports full/cheap
   cap randomization and early stochastic actions. Try full search with
   probability 0.25 and cheap search otherwise; only full positions with known
   terminal outcomes train. Start from measured full256/cheap64 or a justified
   better teacher, not mandatory128. Freeze finite game/call and replay budgets.
   Expected cap is 112 rather than 256 in this example; actual calls, useful
   targets, and game length determine saving. PCR was unrun in the closed
   study and has no established Splendor strength benefit.

Use a second branch only after the first result changes the decision. A clear
critic problem can justify one value-weight/target calibration change instead.
Inspect terminal Brier/calibration, root bias, and searched disagreements.
Do not launch a loss-weight grid, architecture sweep, and corpus at once.
Dev loss selects an epoch; fresh played games select an agent. Labelled rows
and repeated positions are not independent game counts.

Prefer a warm start to scratch architecture. A larger Entity or tactical
curriculum is allowed if a clear fitting bottleneck remains and it fits the
branch budget. Immediate wins, noble activation, and opponent win threats
are possible cheap labels. A sampled-world short-horizon result is not a
forced win under hidden information. Do not build a curriculum when saved
models and the working search pipeline offer the better next step.

## Track C: use the Mac without wasting it

Observed host: M4 Pro, 14 CPU cores, 48 GiB unified memory. One owner assigns
CPU, GPU, RAM, ports, outputs, and binaries. Five helpers do not mean five
full-speed heavy experiments. Do not stop unrelated services. Check process
identity before recovery.

Start Entity canonical collection/arena at 64 workers with the existing MPS
batch32 service. Workers wait on inference; core count is not a useful ceiling
by itself. Start native AlphaZero matches at 8 CPU workers; test 16 on a short
excluded timing workload if Entity occupancy is low. AlphaZero Python/Numba/
ONNX processes also consume CPU/RAM. Do not default to 64 native processes.

Measure useful requests/batch, padding, queue wait, batches/second, complete
games/second, and memory pressure. The service has separate model queues and
synchronous replies; multi-model jobs split occupancy. The native scheduler
uses static shards. A small dynamic shard queue with complete seat blocks can
reduce tails. Preserve block seeds and ordered records. Reuse this harness.

Try existing delay0/0.25/1 ms or better scheduling before a rewrite. Batch/
backend changes can alter floating-point outputs. Exact output and trajectory
parity are required to claim unchanged search semantics. A numerically
different backend can be a declared new candidate: verify finite outputs,
legality, public inputs, and bounded numerical agreement, then select and
confirm with that exact backend. Do not silently switch final kernels.

Use MPS for Entity training or inference as the primary GPU job. CPU-native
small-model search or offline audits can overlap. Measure total completion
time before overlapping MPS training with MPS inference. Four-minute fits
save little beside a multi-hour collector. The old small-network CPU result
does not settle Entity performance. Keep native CPU inference as a fallback.
Free Cloudflare supplies no needed local training hardware here. Hosting/demo
work is outside the critical path.

## Evaluation that can finish and support the claim

Explore with fixed short samples and fresh masters. Confirm **one** final
frozen profile. Do not run 20,000 games for intermediate changes or repeat
internal milestones. Retain seat rotations, shared-win credit, all statuses,
and histories. Reuse replay receipts for unchanged data/checkers; do not rerun
expensive policy search to validate a model-only experiment.

Before final outcomes, save checkpoint/descriptor SHA, service source/config/
device, binary SHA/source fingerprint, AlphaZero pin/checkpoint, search,
seed, sample count, interval rule, lineage, and selection trials. Freeze
**1,000, 2,000, or 4,000 games**, chosen from measured cost and expected margin.
Default to 2,000. Twenty thousand is optional if it fits a useful question.

Use the native summarizer's conservative two-sided Hoeffding envelope over
independent paired setup blocks. Radius is
`sqrt(log(2 / 0.05) / (2 * blocks))`, with two games per block. For example,
62% credit in 1,000 complete games gives a lower bound near 55.93%; 60% in
2,000 gives about 55.71%. Thus a decisive result does not require 20,000 games.
These examples are not predictions. Do not stop at a favorable fixed-sample
interval, append games after an unfavorable result, or use final outcomes to
choose another model.

Every unknown has credit [0,1]; all requested games stay in the denominator.
At most 1% no-action is the existing allowance. Invalid records, missing
rotations, excessive no-action, and external decision-limit errors reject
evidence. Keep failed/interrupted files; never replace a losing or unknown
seed. Native runners stop on invalid play and can leave partial shards.
Investigate, then finish the original planned blocks with explicit resume
provenance or report failure. A partial run is not the planned final test.

Native 124-turn score-cap results belong to unchanged AlphaZero's rules.
Report their count/native credit and a second bound treating caps as unknown.
They are not canonical victories. Replay all final legal actions, chance
draws, states, and rewards. Bootstrap intervals are supplemental; the
conservative bound controls the claim. Add a modest fresh canonical Entity
comparison if feasible, without delaying the external proof.

## Sol and Luna task split

| Owner | Finite task | Output |
|---|---|---|
| Sol | Choose branch, own heavy queue, integrate, freeze, judge claims | run.json, selection log, final report |
| Luna 1 | Check artifacts, datasets, pins, split IDs | Hash/split receipt |
| Luna 2 | Profile service/scheduler; implement one bounded change | Patch, whole-game timing, parity or new-backend receipt |
| Luna 3 | Expose search controls or add learner-actor collection | Patch, targeted correctness/public-input checks |
| Luna 4 | Prepare one training branch and audit loss/calibration | Data/recipe manifest, diagnostics |
| Luna 5 | Audit final records, costs, statistics, reproduction | Independent evidence audit |

These are roles, not a requirement to start five helpers. This planning run
used three Luna research agents. Findings were checked against repo code and
reports. An initial E95-small-model recommendation was rejected because Entity
already used that data and had the stronger confirmed representation. Old
small-model GPU results were not applied to Entity. Only Sol changes acceptance
rules or schedules expensive work. Helpers do not restart the closed study or
create recurring jobs or extra GPU load.

## Research context and excluded work

The pinned audit shows AlphaZero implements visits, root-Q/terminal mixing,
recent replay, cap randomization, exploration, forced-playout pruning, symmetry,
and network gating. It does not use a learned per-action-Q output. Source and
metadata do not prove complete checkpoint training lineage. See
[the audit](research/training_strategy/upstream-audit.json).
[KataGo](https://arxiv.org/abs/1902.10565) supplies the external basis for more
efficient cap-randomized training; transfer to Splendor is a hypothesis.
[Gumbel AlphaZero](https://openreview.net/forum?id=bERaNdoegnO) motivates
policy-improvement search, but does not mandate128 or guarantee improvement
with biased values. Local E80 target/execution failure still matters.

Do not start with hidden-card heads, history, generic residual scaling,
loss-only claims, demo polishing, a new benchmark suite, or a full upstream
training rewrite. Generic color shuffling is not a safe fixed-catalogue
symmetry. Augmentation must preserve card/noble distributions and remap
observations/actions/labels together. Never train from a final test.

## Delivery

Save one endpoint with lineage and a runnable recipe, raw final records,
replay/statistics receipts, exact search/backend, costs, and negative results.
State whether the decisive criterion passed. Update the research strength
registry only with confirmed evidence and explicit profile. Save a recoverable
handoff and push it. If AlphaZero still wins, deliver the strongest measured
endpoint and specific failure. Current evidence does not guarantee a win.
