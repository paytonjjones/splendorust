# Unchanged AlphaZero under its native rules

Status: complete. The fresh 20,000-game confirmation and both 2,000-game
controls completed and passed native replay.

The benchmark adapts SplendoRust to the pinned AlphaZero game. It does not adapt
AlphaZero. The upstream pretrained checkpoint, network, MCTS, legal generator,
transitions, rewards and search settings stay unchanged. Actual games use the
upstream Python referee. Canonical published Splendor remains the default, and
the main learned-strength loop is unchanged.

## Implementation

The new `Environment` interface supplies observations, sampled states, actions,
legal sets, transitions and terminal rewards. `PolicyValue` supplies the model
and policy evaluation. One PUCT expansion, selection and backpropagation kernel
serves both canonical and native environments. The native Rust rules support
search simulations; they do not referee the recorded games.

Both environments use the same frozen E56 policy/value model and weights.
The native model translator keeps the existing 392-feature, 81-policy-output,
two-value-output contract. It sorts noble IDs for model input, as the existing
canonical encoder does, while native rules retain the upstream noble slot order.
No weights or exploration coefficients were tuned on benchmark outcomes.

The native entry point supports two-player, fixed-iteration search. It starts a
fresh tree for each decision. The confirmed E56 configuration has no persistent
tree, rollout or time limit. Canonical history and cycle filters stay in the
normal canonical entry point. This does not claim support for every optional
agent mode in every future environment.

See [README.md](README.md) for each native action ID, rule difference,
observation field, determinization rule, reward mapping and RNG stream.

## Frozen protocol

Code revision: `9c354b6181904c915db41a607df03ec0a1dbf496`.
Base revision: `d9d4e4d`. Branch: `codex/alphazero-native-environment`.
Profile: `alphazero-native-32a27ac-v1`.

| Item | Frozen value |
|---|---|
| SplendoRust model | Confirmed E56, `research/e56/model/model.bin` |
| Model SHA256 | `055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41` |
| SplendoRust primary search | 128 iterations, depth 16, three sampled worlds, cpuct 0.4, FPU reduction 0.02965, uniform prior 0, no rollout or persistent tree |
| Higher-search control | Same model and settings; 800 iterations |
| Upstream source | `lyquentxy/splendor`, revision `32a27ac1f85d5de2766cc5f60c2bf04e557f7836` |
| Upstream checkpoint SHA256 | `6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07` |
| AlphaZero search | 800 simulations, cpuct 0.8, FPU 0.0593, three universes, full search, no forced playouts, normal memory cleanup |
| AlphaZero selection | Upstream pit argmax; temperature 0.5 for the first six total turns, then 0 |
| Runtime | Pinned Rust 1.98.1/Cargo.lock; CPython 3.11.13 and pinned inference dependencies |

Every setup block has both seat rotations. Setup, policy and referee chance
streams are distinct. Settings were frozen before the screen. Fresh master
seeds are 4110000000 for the screen, 4120000000 for confirmation and 4150000000
for the exploratory higher-search control. No schedule outcome selects settings
for the next schedule.

SplendoRust sees only the acting player's legal observation and public history.
Unknown opponent blind reservations and remaining-card membership are sampled
without replacement. The policy schema rejects real blind IDs, deck masks,
setup seeds and referee RNG fields. AlphaZero receives its normal native board,
which includes both players' private reservation identities and true unordered
remaining-card membership. This information difference is explicit. There is no
stored future deck sequence in the native game.

## Validation

- Differential checks covered 9,204 upstream positions and 312,879 legal branch
  successors across 100 complete trajectories. All 81 action IDs were covered.
  Legal sets, native board features, redacted observations, score changes and
  terminal rewards matched. Signed shared rewards use floating-point tolerance.
- Targeted Rust tests cover small token takes, full-turn returns, colored-first
  payments, reserve at token cap, pass, all eligible nobles on purchases,
  termination at the native turn cap, tied scores and purchased-card tie breaks.
- Hidden-information tests vary real blind reservations while keeping the public
  observation and policy seeds fixed. The sampled inputs and full search choices
  match. Extra hidden fields and opponent blind IDs are rejected.
- Canonical parity checked all 15,700 decisions in 200 games against a release
  worker built from base `d9d4e4d`. Every choice and state matched.
- Format, strict workspace Clippy, release workspace tests with all features,
  default release tests and the original diagnostic Python tests passed.
- The completed screen replay checked all 2,000 games and 110,886 transitions.

Exact counters and logs are in `differential.json`, `canonical-parity.json`,
`validation/` and each schedule's `replay.json`. The frozen manifest records
source, binary and model hashes, dependency versions, compiler details and all
tracked upstream file hashes.

The first development smoke used native noble slot order directly in the model
encoder. That did not preserve the existing E56 feature contract. Those records
and the interrupted scaling trial remain under `development-native-slot-order*`
and are excluded from strength evidence. The correction and shared-feature
regression test preceded the freeze. No AlphaZero change was made.

## Fresh results

All three schedules completed. Every game passed replay against the unchanged
upstream referee. There were no unsupported, invalid, blocked or incomplete
games. AlphaZero used its unchanged 800-simulation setting in every schedule.
Win credit gives one credit to a sole winner and half to each shared winner.

| Schedule | SR iterations | Games | Completion | SR credits | SR win credit | Conservative 95% interval | Paired bootstrap 95% interval |
|---|---:|---:|---:|---:|---:|---|---|
| Screen | 128 | 2,000 | 100.00% | 464.0 | 23.200% | 18.91%–27.49% | 21.43%–25.00% |
| Primary confirmation | 128 | 20,000 | 100.00% | 4,679.0 | 23.395% | 22.04%–24.75% | 22.82%–23.98% |
| Higher-search control | 800 | 2,000 | 100.00% | 755.5 | 37.775% | 33.48%–42.07% | 35.65%–39.90% |

The primary endpoint is the fresh 20,000-game confirmation, with 10,000
independent setup blocks and both seat rotations. The conservative interval uses
Hoeffding's bound on block credits in [0,1]. The bootstrap resamples whole setup
blocks. These intervals assume independent blocks under the declared RNG streams.
The screen and higher-search control are separate endpoints; they are not pooled.

Unchanged AlphaZero is stronger than frozen E56 at the primary settings in
this native profile. The conservative upper bound for E56 is below 50%.
The information difference prevents an equal-information claim. The result
does not rank the agents under canonical published Splendor.

The pre-registered higher-search control used the same E56 weights and
800 iterations. Its win credit was 37.775%. It is an exploratory
compute control, with fresh seeds and a smaller schedule. It is not a training
gain, a paired comparison with the primary schedule, or an equal-compute claim.

| Schedule | SR seat 0 credit | SR seat 1 credit | Terminal categories | Replayed moves |
|---|---:|---:|---|---:|
| screen | 22.950% | 23.450% | native_score: 2,000 | 110,886 |
| confirmation | 23.425% | 23.365% | native_score: 19,999, native_turn_cap: 1 | 1,108,016 |
| higher-search | 41.100% | 34.450% | native_score: 2,000 | 112,044 |

`native_score` means the 15-point condition. `native_turn_cap` means the
upstream 124-turn condition. Both use the upstream score and purchased-card
tie break. No cap is assigned a fabricated canonical outcome.

The sole cap case was confirmation game 3188, block 1594, rotation 0.
At turn 124, E56 had 1 point and AlphaZero had 12. E56 passed 47 times;
AlphaZero passed 35 times. The unchanged native referee awarded AlphaZero
the win. The last legal sets and an extra state/reward check are saved in
`cap-review.json`. Treating this one result as unknown gives primary
credit bounds of 23.395%–23.400%; the conservative upper bound remains
below 50%. This sensitivity check does not replace the native protocol.

## Recorded runtime

| Schedule | Eight-worker wall seconds | Games/second | SR policy seconds, sum | AlphaZero policy seconds, sum | SR simulations | SR inferences |
|---|---:|---:|---:|---:|---:|---:|
| screen | 500.56 | 3.996 | 275.28 | 3,585.73 | 7,096,704 | 6,950,575 |
| confirmation | 6,278.46 | 3.185 | 4,202.48 | 45,580.61 | 70,913,024 | 69,462,491 |
| higher-search | 836.13 | 2.392 | 1,827.51 | 4,693.16 | 44,817,600 | 43,048,320 |

Policy seconds are measured elapsed time per decision, summed over concurrent
games. They are not isolated CPU seconds. Schedule wall time includes worker
startup but excludes the later replay, compression and summary steps. Search
budgets are fixed; runtime is reported rather than used to assert equal compute.

## Runtime control

The same 128-game schedule at 1, 4 and 8 processes produced identical actions,
state hashes, public-input hashes, rewards and work counts. Only timing fields
differed. All three record sets passed native replay.

| Processes | Wall seconds | Games/second |
|---|---:|---:|
| 1 | 230.26 | 0.556 |
| 4 | 75.66 | 1.692 |
| 8 | 46.33 | 2.763 |

Times include worker startup, lazy compilation and process communication.
The main learning job ran on the same host during this work. The measurements
are not an isolated hardware throughput claim. Equal iteration counts are not
equal compute: the two searches and network runtimes differ.

## Scope and reproduction

E56 was confirmed under canonical rules. No native-rule training was done.
This is a transfer benchmark for the same frozen model.

This profile supplies a complete native opponent and a reusable search/rules
boundary. It measures these frozen agents under native rules and the stated
information difference. It does not establish canonical Splendor rank,
equal-information strength, equal-compute strength, or a rank for all
AlphaZero-family implementations. The original unchanged canonical diagnostic
comparison in `../REPORT.md` and `../results/` is preserved.

Use the build and validation commands in [README.md](README.md). Each schedule's
`plan.json` and `execution.json` contain the exact commands and worker results.
Raw histories include the initial native board, every action, chance seed,
state digest, public-input digest, score, reward and policy work count. Final
records are stored in lossless deterministic gzip archives; `archive-index.json`
records compressed and exact raw hashes. The original raw files remain in
this execution worktree.


The final audit command checks the frozen files, all lossless archives and each
completed schedule's replay evidence:

```sh
local/strength/inference/bin/python benchmarks/strength/native/audit_results.py \
  --runtime --output benchmarks/strength/native/final-audit.json
```

`artifact-manifest.json` contains the exact hashes of the final documentation,
commands, validation logs, summaries, replay evidence and compressed records.
The compiled source stays pinned to the frozen code revision above; the later
results commit does not change that binary or the benchmark settings.
