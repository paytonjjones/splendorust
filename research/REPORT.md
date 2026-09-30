# Playing-strength research status

The strongest completed development candidate is `transfer-pool3`; its final
confirmation is running. The last confirmed research candidate is
`neural-selfplay`: a native Rust policy/value network with information-set PUCT, 128 simulations, depth 16 and eight heuristic
rollout turns. Its checkpoint is E28. E26 `neural-rollout` remains the last
agent to pass the strict no-incomplete-games promotion gate. Original `search128` remains available
and unchanged. This is a two-player result; other player counts use the Strong
fallback and have no learned-strength claim.

## Confirmed results

| Comparison | Requested / complete games | Candidate credit on complete games | Conservative 95% interval |
|---|---:|---:|---:|
| E24 learned value vs original Search128 | 20,000 / 19,999 | 79.30% | 78.33–80.27% |
| E26 neural rollout vs E24 learned128 | 20,000 / 20,000 | 57.73% | 56.59–58.86% |
| E26 neural rollout vs original Search128 | 20,000 / 19,999 | 83.00% | 82.09–83.91% |
| E28 self-play model vs E26 neural rollout | 20,000 / 19,999 | 54.17% | 53.05–55.29% |

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
2.34x faster with identical saved outputs and playing records. No transfer
agent has a final confirmation or an external leadership claim yet.

E36's fresh internal screen completed all 2,000 games. At 128 simulations,
`transfer-pool3` earned 81.55% against E28, conservative interval
77.85–85.25%. The reserved 20,000-game confirmation and 400-game external
comparison are running. E37 tested depth 64 against depth 16 at 800
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

This command repeats the completed screen; it must not guide new tuning. A 400-game external run and final
internal confirmation are still required before selecting it as the final agent.
The committed binary weights permit evaluation without the Python training
environment or large training datasets.
