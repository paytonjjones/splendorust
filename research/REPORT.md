# Playing-strength research status

The confirmed research champion is E56 (`research/CHAMPION.json`). It scored
55.26% against the prior trained cycle 0 champion in 20,000 complete paired
games at 128 simulations. The 95% interval is 54.13–56.39%. The strict gate
passes. This establishes a second learning gain. E54 achieved the main gain
with 281,432 positions from 5,000 games by an 800-simulation teacher. E56 then
advanced after a provisional 51.15% screen over E54. The independent milestone
confirms the endpoint's gain over the fixed prior champion. It does not confirm
the small E56-over-E54 difference by itself. The transferred model remains a
bootstrap. The architecture still has 142,406 parameters.

E57 endpoint controls scored 95.64% against frozen Search128 (1,996 of 2,000
complete games) and 97.625% against Strong (2,000 complete games). At 16 NN
simulations, it scored 82.88% against Search128 (1,995 complete games).
Incomplete outcomes remain unknown. On the same 568 observations, median
decision cost was 0.835 ms for NN16, 1.137 ms for Search128, and 6.265 ms for
NN128. Shared host timings do not establish universal compute equivalence.
Native controls remain separate from external rankings.

The unchanged 400-game AlphaZero profile produced 209 complete games, 191
unsupported games, and 59.81% conditional credit. All-requested point bounds
are 31.25–79%. The paired bootstrap missing-outcome envelope is 26.625–83%.
All 400 saved histories passed canonical replay checks. No external rank is
established. `research/e57/` contains the raw evidence.

E54 teacher collection took 963.50 s for 6,000 games and 337,953 positions:
6.23 games/s and 350.75 positions/s. Training took 95.94 s and the 2,000-game
screen took 48.49 s. With a saved corpus, model-to-screen takes about 2.4
minutes. E56 collected 2,000 fresh games in 315.37 s, trained in 107.84 s,
and screened in 46.15 s. Its 20,000-game milestone took 523.34 s and stays
outside the inner loop. E55's random hidden-view control was rejected at
49.525%; measured sensitivity changed little. Current evidence supports more
strong-teacher data. E58 used the confirmed model as an 800-simulation teacher and advanced
provisionally at 51.8% over E56 in 2,000 complete games. Its 95% interval
is 47.49–56.11%; this is not a confirmed gain. E56 stays the champion.
E59 tested 50 epochs on the same corpus and advanced provisionally at
51.3% over E58 (2,000 complete games,CI47.11–55.49%). It selected epoch7
and barely changed fit KL. Keep10epochs as the normal training budget. E60 found 24.1% mean pairwise
teacher policy TV on 62 fixed observations. E61 tests two-teacher averaged
targets with all E58 trajectories and inputs held fixed. Its corpus generation
is active. These controls will guide the next structural change.
All negative results and prior champion files remain saved. Original Search128
and core rules are unchanged. Learned evidence is for two players only; other
player counts use Strong.

## Confirmed results

| Comparison | Requested / complete games | Candidate credit on complete games | Conservative 95% interval |
|---|---:|---:|---:|
| E56 learned endpoint vs cycle0 champion | 20,000 / 20,000 | 55.26% | 54.13–56.39% |
| E24 learned value vs original Search128 | 20,000 / 19,999 | 79.30% | 78.33–80.27% |
| E26 neural rollout vs E24 learned128 | 20,000 / 20,000 | 57.73% | 56.59–58.86% |
| E26 neural rollout vs original Search128 | 20,000 / 19,999 | 83.00% | 82.09–83.91% |
| E28 self-play model vs E26 neural rollout | 20,000 / 19,999 | 54.17% | 53.05–55.29% |
| E36 bootstrap teacher vs E28 self-play model | 20,000 / 19,997 | 80.23% | 79.24–81.22% |

These comparisons use fixed simulation counts. Neural tree search costs more per
simulation than original root-only search. The E26 versus learned128 comparison
passed `scripts/promote.py` without an exception. Comparisons with an
incomplete game retain the strict gate rejection. Their intervals retain every
requested game and bound the missing outcome; the user permitted further
research despite such gaps. No victory was assigned to a blocked game.

Against frozen external AlphaZero (800 simulations), E26 won 14 of 240 complete
games in the unchanged 400-game schedule. There were 160 unsupported games:
156 native actions outside the published legal set, one voluntary return and
three unsupported Return choices. Candidate finite-schedule credit bounds are
3.5–43.5%; the paired bootstrap missing-outcome envelope is 1.75–48.5%. This
cannot support a best-in-class claim. The external planning rules and our actual
transitions differ, and iteration counts are not equal compute.

The matched one-millisecond search-loop confirmation earned 76.62% against the
original search algorithm in 20,000/20,000 complete games, with a 95% interval
of 75.60–77.63%. Wall-clock runs are nondeterministic,
include shared-host interference, and cannot pass the deterministic promotion
gate. Both implementations check time between simulations; preparation and
final selection are outside the loop timer, and a final simulation can overrun.

## Current experiments

E28 distilled 256-simulation E26 self-play, using root visit probabilities and
selected-edge values. All 6,000 training and 1,000 development games completed,
producing 167,616 and 27,934 observation-only positions. Independent confirmation
showed a further internal gain. Its one missing outcome remains bounded and the
strict rejection remains intact. Its external rerun earned 19.5 credits in 233 complete games out of 400
(8.37% conditional); all 167 unsupported results remain unknown.

E30 transfers the existing external version-80 pretrained network into native
Rust inference. It is an attributed MIT-licensed upstream model, not a new model
trained from scratch. All 90 cards are matched by semantics. On 94 fresh game
positions, the observation-derived encoding matches upstream exactly and logits
agree within 0.000007. The first absolute-logit check failed on artificial extreme
inputs; the failure and subsequent normalized-output checks are preserved.

Transferred policy alone is weak. Adding search and eight heuristic rollout
turns scored 64.75% against E28 in a preliminary 200-game screen. After a transfer-only key correction, 1,999 of 2,000 fresh games completed
and the candidate scored 67.23% among complete games: this network uses the
turn count, so its tree key must retain that field. E31 separately tests the
source network's exploration parameters after scaling from [-1,1] to [0,1].
E31 earned 68.80% against E28 in 2,000 complete development games. The
three-world sampling variant then earned 62.52% against E31 in 2,000 complete
development games, interval 58.37–66.68%. At 800 simulations its small external
screen earned 7.5 credits in 14 complete games out of 20, with six unsupported. Native inference now runs
2.34x faster with identical saved outputs and playing records. The transfer candidate now has a fresh internal confirmation. Its external
rerun earned 93.5 credits in 202 complete games out of 400 (46.29% conditional),
with 198 unsupported. Finite-schedule bounds are 23.38–72.88%; the paired
bootstrap missing-outcome envelope is 19.13–77.25%. This does not establish
external leadership.

E36's fresh internal screen completed all 2,000 games. At 128 simulations,
`transfer-pool3` earned 81.55% against E28, conservative interval
77.85–85.25%. Both reserved assessments are complete, with all raw records retained. E37 tested depth 64 against depth 16 at 800
simulations: 51.25% in 200 complete games, interval 30.38–72.12%. No gain
was shown; retain depth 16. E38 tested eight sampled worlds against three
on independent development seeds: 47.25% in 200 complete games, with no
gain shown. Retain three worlds. These tests do not change E36's candidate.

## Rejected experiments retained

- E23 learned leaf without cycle handling: strong conditional score but repeated
  token cycles and incomplete games.
- E25 first residual network: weaker play than original Search128.
- E27 external-teacher fine-tuning: better prediction scores but only 38.75%
  against E26 in 200 complete games; later epochs overfit.
- E38 eight sampled worlds: 47.25% against three worlds in 200 complete
  games; no gain shown.
- E33 dynamic first-play estimates: 46.5% against the fixed estimate control
  in 200 complete games; no gain shown.
- E37 depth 64: 51.25% against depth 16 in 200 complete games; no gain shown.
- E29 persistent observation-matched tree: 49.75% against E26 in 200 complete
  games. No demonstrated benefit; not selected.

## Evidence and reproduction

`EXPERIMENTS.md` contains hypotheses, seed reservations and decisions. Keep the
raw reports, trained checkpoints, negative results and source/record hashes.
The large datasets and frozen executables remain under ignored
`local/research/`; they have not been deleted. E26's strict promotion decision
and its hashes are in `research/e26-gate/decision.json`. The current generator
reproduces both E23 datasets byte for byte. Native neural inference matches
PyTorch within four millionths on the saved parity fixtures.

Build with the pinned Rust toolchain and Cargo.lock. To reproduce the last
strictly promoted E26 control against the original baseline:

```
cargo build --release --locked --bin splendor
target/release/splendor compare --agent-a neural-rollout --agent-b search128 \
  --players 2 --games 20000 --iterations 128 --depth 16 \
  --seed 1303000000 --threads 4 --output reproduced-original-search.json
```

Reusing that final schedule verifies a result; it must not supply new training
positions or guide tuning. Timings vary by host load. `research/README.md`
describes features, algorithms and training commands.

## Evaluate this checkpoint

The strongest completed development candidate is `transfer-pool3`. It uses the
credited upstream network and three sampled root worlds. For a quick comparison:

```
cargo build --release --locked --bin splendor
target/release/splendor compare --agent-a transfer-pool3 --agent-b neural-selfplay \
  --games 2000 --iterations 128 --depth 16 --seed 628000000 --threads 4 \
  --output local/research/review-comparison.json
```

This command repeats the completed screen; it must not guide new tuning. Its completed internal confirmation justifies its use as the research teacher;
its strict incomplete rejection and uncertain external rank remain intact.
The committed binary weights permit evaluation without the Python training
environment or large training datasets.


## Current priority: fast self-improvement

The new loop is implemented. Its first 5,000-game learning cycle has completed fresh
confirmation. Automatic 20k/75k follow-on collection was stopped under the
measurement-first objective. Choose the next teacher budget or corpus size
from playing gain per total wall-clock, then train, export and evaluate again.
Each cycle uses the strongest selected checkpoint as its teacher, with earlier
training shards as replay. Models load once per process; new weights require no
Rust recompilation. Raw data and checkpoints remain under
`local/research/flywheel-e40`; the run plan, receipts and stage logs identify them.

Two miniature cycles verified training/export/parity/rejection and incumbent
retention. They provide no strength claim. Native trained-model logits agree
with PyTorch within 0.000010 on 128 held-out positions. A repeated completed run
skipped data/training/gates. Runtime-loaded bootstrap weights produce the same
32 ordered playing records as the embedded model. The data writer reproduces
identical bytes with one and four threads. Rust and Python checks pass.

E39 measures total Main decision time on the same fixed observation workload:
median Search128 0.707 ms, neural rollout128 2.327 ms, bootstrap128 6.843 ms.
The bootstrap is about 9.7x more expensive at equal simulation counts. These
are latency measurements, not equal-compute playing results. The learning loop
records collection rows/sec, simulations, inference calls, training time and
evaluation time so further work can target useful iterations per wall-clock.


Cycle 0 collected 5,000 training and 1,000 development games, all complete,
in 631.31 seconds. Training took 92.40 seconds. Its 20,000-game confirmation
scored 54.71% against the bootstrap, conservative CI 53.58–55.84%, with one
blocked game retained as unknown. It is selected for research; the strict
incomplete-game rejection remains. Full iteration time was 3039.81 seconds,
including 2101.84 seconds of confirmation. Conditional relative Elo gain was
32.83 [24.94,40.74] for this pairing and compute budget, not a global rating.

E42 tested a second learning iteration with budget256/800 teachers. The256
challenger scored 51.89% in 5,000 complete games, CI 49.44–54.34%; retain the
incumbent. The800 arm selected epoch zero with identical incumbent bytes;
its arena result is a self-comparison. E43 aligned development targets and
selected a trained challenger. It scored 52.80% in 5,000 complete games,
CI 50.37–55.23%; retain the incumbent because the lower bound is below 51%.
A second accepted gain has not been established. All checkpoints are preserved.

Normal inner iterations now use one fixed 2,000-game paired gate with no
mandatory confirmation. Inconclusive results retain the incumbent and move to
the next model. Larger independent confirmations remain outside this loop for
milestones, external claims, and ambiguous results. E44 measured self-play and
arena throughput at 4/8/12/14 threads and selected 14 as the driver default.

**E44 completed:** Two serial repeats at identical schedules preserve self-play
bytes and ordered arena records across4/8/12/14 threads. Mean games/s:
selfplay: 4 threads 9.40, 8 threads 18.16, 12 threads 22.34, 14 threads 23.35. Best14: 2.48x versus four.
arena: 4 threads 9.61, 8 threads 18.45, 12 threads 20.76, 14 threads 24.15. Best14: 2.51x versus four.
Set the learning driver default to14 threads on this host. These are workload
measurements, not strength results; raw records and binary hashes are saved.

E45 tests a425,747-parameter gated residual student trained from scratch on
185,354 saved stronger-search positions. Native inference is1.93x faster;
128-simulation decisions are1.85x faster. It scores6.40% against the incumbent
in1,999/2,000 complete games. Reject; the missing game stays unknown. E46
decodes packed deck bytes into bits and adds frozen-teacher distillation. It
scores33.375% in2,000 complete games, CI29.27–37.48%. Reject despite better
held-out prediction fit. Neither result proves a faster improvement loop.

E47 adds two teacher-initialized residual blocks. It scores51.225% in2,000
complete games,CI46.89–55.56%,and increases inference cost. Reject.

E48 uses the same frozen model at256 and800 simulations against128. Results
are60.20% and70.625%,with2,000 complete games each and lower bounds56.02% and
66.62%. More search makes stronger teachers. These controls use more compute;
they are not training gains or matched-compute improvements.

E49 freezes the value function and trains the policy head. Its54.5% screen is
ambiguous; fresh5,000-game confirmation scores51.68%,CI49.26–54.10%. Reject.
E50's matched full-network control scores50.65% in2,000 complete games. Reject.
E51 retains the frozen critic but concentrates late targets on maximal visits.
It scores49.95% in2,000 complete games,CI45.65–54.25%. Reject. Training plus gate
takes148.07s with reused data; initial collection and validation are separate.

All models, source snapshots and raw results remain available. At E51, the incumbent
was unchanged and repeated gain was unproved. E52 then tested separate
policy/value feature encoders. The current status is at the top of this report
and in [HANDOFF.md](HANDOFF.md).

Agent2's03326dd CPU kernel is integrated as5d02e8c. Its shared-Mac confirmation
reports60.5% self-play and65–81% arena throughput gains, with exact data and
record parity. The production commit includes no batching or accelerator code.
E52 then trains independent policy features with an exact frozen critic. It
scores51.10% in2,000 complete games,CI46.92–55.28%; reject. Training98.77s and
gate66.46s. On the same saved inputs, median inference is39.57us
versus31.25us;128-simulation decision cost is1.273x.
The timing uses the faster kernel on both models and is conditional on this host.
E53 tested the small budget800-only corpus: 51.55% over 2,000 complete
games, CI47.34–55.76%. Reject under its registered rule.

Evaluator feedback changed the next work: stop architecture changes, separate
exploratory lineage selection from fixed-champion confirmation, and collect a
comparable-volume800-simulation teacher corpus. E54 collected5,000 training
and1,000 development games. E55 is the paired multi-view input control.
The original data and search trajectories remain exact when sidecars are saved.

In the first1,000 teacher games,18.5% of rows have an opponent blind reservation.
Across512 sampled blind observations,eight encodings give mean legal-policy TV
5.03%,argmax disagreement8.45%,and mean raw value range0.230. Inputs without
opponent blind reservations are invariant. This establishes conditional input
sensitivity and its measured prevalence; causation of training failure remains
an experimental question. The fixed champion and earlier decisions are intact.

E54's comparable-volume800 teacher corpus yields a56.775% strict screen pass,
all2,000 games complete,CI52.51–61.04%. The student uses the same bootstrap
architecture and128 simulations as the fixed champion. Collection costs
963.50s,training95.94s,and gate48.49s.
This supports the larger stronger-teacher experiment after the small-corpus
failures. The independent E56 endpoint assessment later passed (see below). Dev's
one blocked game keeps37 outcome labels unknown; it does not affect screen
completion. Models, raw gates, source snapshots and dataset hashes are saved.

E55's paired multi-view control scores49.525% against E54 in2,000 complete
games and is rejected. Its development input sensitivity changes very little.
E56 trains from E54 with1,000 fresh800-simulation teacher games plus the5,000-
game replay corpus. Its51.15% complete screen advances only the provisional
lineage. The independent fixed-champion20,000-game assessment passed at55.26%,
all games complete,CI54.13–56.39%. Strict promotion accepts E56.
Small screen increments and external rank remain separately unconfirmed.
