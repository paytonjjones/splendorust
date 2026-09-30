# External playing-strength benchmark

Date: 2026-09-29. Baseline: `origin/main` at `3d1a339`. Default rules and
Search/Strong/Random source are unchanged. All planned schedules completed.
The result does **not** establish an external rank or state-of-the-art status.

## Measured confirmation results

Candidate is current Search (128 simulations). Opponent iteration counts
are separate cost models. Intervals resample paired setup blocks. Every
missing outcome is bounded between zero and one. Conditional credit applies
only to complete games and cannot rank an unfinished schedule.

| Match | Requested | Complete | Unfinished | Search/native MCTS conditional credit | All-requested credit bounds | 95% block interval with missing bounds |
|---|---:|---:|---:|---:|---:|---:|
| Search vs Strong, 2 players | 1000 | 1000 | 0 | 70.30% | 70.30%–70.30% | 67.40%–73.20% |
| Search vs Random, 2 players | 200 | 198 | 2 | 98.48% | 97.50%–98.50% | 94.50%–100.00% |
| Search vs AlphaZero, 2 players | 400 | 211 | 189 | 2.84% | 1.50%–48.75% | 0.50%–53.75% |
| Search vs 2 AlphaZero, 3 players | 120 | 5 | 115 | 0.00% | 0.00%–95.83% | 0.00%–99.17% |
| Search vs 3 AlphaZero, 4 players | 120 | 3 | 117 | 33.33% | 0.83%–98.33% | 0.00%–100.00% |
| Search vs Seal256 MCTS500, 2 players | 200 | 9 | 191 | 100.00% | 4.50%–100.00% | 2.00%–100.00% |
| Native Seal256 MCTS2000 vs native random | 400 | 395 | 5 | 91.14% | 90.00%–91.25% | 87.00%–94.00% |

AlphaZero wins 205 of the 211 completed two-player games; Search wins 6. There are no shared wins in this run.
Even if every unfinished game were assigned to Search, its finite-schedule
credit would be at most 48.75%. The population interval still crosses 50%,
and compute differs, so this is suggestive evidence rather than a firm rank.

Final schedules contain zero invalid games and zero capped games.
Each unfinished status remains in the uncertainty bounds.

## Full seat rotation

Each setup is played with Search in every seat. Native control rotates MCTS
through both seats. Entries show complete/requested games and earned credit.
Credit is not awarded to unsupported, blocked, capped or invalid games.

| Match | Seat | Complete / requested | Win credit | Sole wins | Shared wins |
|---|---:|---:|---:|---:|---:|
| Search vs Strong, 2 players | 1 | 500 / 500 | 353.00 | 353 | 0 |
| Search vs Strong, 2 players | 2 | 500 / 500 | 350.00 | 350 | 0 |
| Search vs Random, 2 players | 1 | 99 / 100 | 97.00 | 97 | 0 |
| Search vs Random, 2 players | 2 | 99 / 100 | 98.00 | 98 | 0 |
| Search vs AlphaZero, 2 players | 1 | 105 / 200 | 2.00 | 2 | 0 |
| Search vs AlphaZero, 2 players | 2 | 106 / 200 | 4.00 | 4 | 0 |
| Search vs 2 AlphaZero, 3 players | 1 | 1 / 40 | 0.00 | 0 | 0 |
| Search vs 2 AlphaZero, 3 players | 2 | 1 / 40 | 0.00 | 0 | 0 |
| Search vs 2 AlphaZero, 3 players | 3 | 3 / 40 | 0.00 | 0 | 0 |
| Search vs 3 AlphaZero, 4 players | 1 | 1 / 30 | 0.00 | 0 | 0 |
| Search vs 3 AlphaZero, 4 players | 2 | 0 / 30 | 0.00 | 0 | 0 |
| Search vs 3 AlphaZero, 4 players | 3 | 2 / 30 | 1.00 | 1 | 0 |
| Search vs 3 AlphaZero, 4 players | 4 | 0 / 30 | 0.00 | 0 | 0 |
| Search vs Seal256 MCTS500, 2 players | 1 | 6 / 100 | 6.00 | 6 | 0 |
| Search vs Seal256 MCTS500, 2 players | 2 | 3 / 100 | 3.00 | 3 | 0 |
| Native Seal256 MCTS2000 vs native random | 1 | 198 / 200 | 177.00 | 177 | 0 |
| Native Seal256 MCTS2000 vs native random | 2 | 197 / 200 | 183.00 | 183 | 0 |

## Incomplete and failed integrations

- Search vs Strong, 2 players: statuses `{"complete": 1000}`; reasons `{}`.
- Search vs Random, 2 players: statuses `{"complete": 198, "no_legal_action": 2}`; reasons `{"published rules have no action": 2}`.
- Search vs AlphaZero, 2 players: statuses `{"complete": 211, "no_legal_action": 4, "unsupported": 185}`; reasons `{"native action outside published legal set": 177, "native policy has no canonical Noble choice": 4, "native policy has no canonical Return choice": 4, "published rules have no action": 4}`.
- Search vs 2 AlphaZero, 3 players: statuses `{"complete": 5, "unsupported": 115}`; reasons `{"native action outside published legal set": 110, "native policy has no canonical Return choice": 3, "native_voluntary_return": 2}`.
- Search vs 3 AlphaZero, 4 players: statuses `{"complete": 3, "unsupported": 117}`; reasons `{"native action outside published legal set": 105, "native policy has no canonical Return choice": 5, "native_pass": 2, "native_voluntary_return": 5}`.
- Search vs Seal256 MCTS500, 2 players: statuses `{"complete": 9, "unsupported": 191}`; reasons `{"native policy has no canonical Return choice": 190, "native_pass": 1}`.
- Native Seal256 MCTS2000 vs native random: statuses `{"complete": 395, "native_no_winner": 5}`; reasons `{}`.

Schuber6: all three saved models load and produce outputs unchanged. Their
46-input/26-output four-card contract has no unchanged twelve-card multiplayer
implementation. This target is unsupported for full-game comparison; no games
or victories are invented. No Double-DQN/prioritized-replay/multi-step code was
found at the fixed revision. The exact shapes, hashes and inference outputs
are in `schuber6-integration.json`.

## Native screening records

The original 100-game MCTS500 and MCTS2000 JSONL and summaries are retained.
Original rates were 88% [82%,94%] and 93% [88%,97%]. The 500-iteration
screen has 99 games with winners and one zero-reward native terminal game.
These original intervals are historical: persistent shuffle RNG meant the
two seat rotations did not share a setup. Audited summaries do not assign
a validated paired interval. The final native confirmation saves identical
initial state fixtures for both rotations and uses independent policy seeds.
Its original complete count was incorrect. The audited summary assigns no
credit to that missing outcome. The original summaries remain historical
artifacts; their retained binary hash cannot prove historical execution linkage.

## Source, checkpoint and reproduction evidence

The practical AlphaZero implementation is `lyquentxy/splendor` at
`32a27ac1f85d5de2766cc5f60c2bf04e557f7836`. The two- and three-player
checkpoints are byte-identical to `cestpasphoto/alpha-zero-general` at
`846b919f781b871da2fff0a05fb4ae069d1a9d45`; the four-player hashes differ.
The two repositories count as one opponent family. No independent training
provenance is established. `audit-manifest.json` records the comparison hashes.
The [associated project report](https://github.com/cestpasphoto/cestpasphoto.github.io#online-splendor-ai) reports ten wins against adapted Lapidary,
not a controlled large benchmark. Its 90%/95% Santorini claims are excluded.

Schuber6 source: `1a3713b95889e05f70c00e806698a6e8d59078f1`.
Seal256 source: `263abc066c563a1c89dba4bdc408446a20ad9d1d`.
See `build-manifest.json` and `index.json` for exact URLs, compiler/runtime,
binary/model hashes, raw-record hashes and per-run build linkage. Run headers
record source fingerprints, adapter hashes, configurations, host and commands.
The native verifier access patch changes no rule body. Raw JSONL contains
every chosen action, winner credit, score, seat, seed block and status.

```sh
python3 benchmarks/strength/setup.py
python3 benchmarks/strength/run_suite.py --output-dir results/strength-reproduction
cargo build --release --locked -p splendor-arena --example strength_replay
python3 benchmarks/strength/verify.py
```

## Compute and information limits

Search uses its current 128-simulation defaults. AlphaZero uses the saved
checkpoint budgets: 800 MCTS simulations for two players and 400 for
three/four players, with upstream ONNX inference. Two-player settings are
`cpuct=0.8`, `fpu=0.0593`, three universes; three/four-player settings are
`cpuct=1.0`, `fpu=0.1`, one universe. Seal256 uses 500
iterations for cross-engine attempts and 2,000 for the native confirmation.
These counts are not equal compute. No controlled fixed-wall-clock strength
comparison was run: native planners lack a matching clock-budget interface,
and unsupported schedules cannot provide an unbiased timed rank. Recorded
wall times include RPC, state sampling/conversion and initial JIT/export work.
`elapsed_seconds` excludes process startup/model load but includes unsuccessful
choices. `policy_seconds` counts only decisions accepted before the stop.
Several fixed-budget jobs shared the host; these times are not speed rankings.

Actual games use the published rules. External planners retain native rules,
which differ on token takes/returns, pass, payment, nobles and termination.
Opponent blind reservations and remaining-card identities are sampled from
public observations, never copied from actual hidden state. One sampled world
per decision is an information adaptation, not native information-set search.
See `PROFILES.md` for every rule/input difference. Core replay checks verify
actual canonical transitions and normal outcomes, not complete native-policy parity.

## Negative results and current position

The first temperature screen used six rounds instead of six total turns;
it is retained and excluded. Early runs used reversible setup-to-policy seed
coupling. Those raw files and the exact earlier runner source are retained
under rejected evidence. The first native confirmation also had unpaired
setups because the shuffle RNG persists. It is retained and excluded; the
final native control copies and records each paired initial state. Final
comparisons use separate setup, policy and
sampling streams and fresh setup seeds. Initial Python 3.12 dependency
resolution failed because ONNX Runtime 1.16.3 has no CPython 3.12 wheel.
Python 3.11.13 and pinned torchvision 0.20.1 resolved the inference environment.

Search has a measured advantage over the internal Strong baseline. The
external comparison intervals include unsupported outcomes, so they do not
establish Search above or below the AlphaZero family or native Seal256.
Schuber6 has no usable full-game result. The published ten-game AlphaZero
claim suggests a useful target, but it does not supply a measured rank here.

The most useful next step is to reduce unsupported boundaries with a separately
validated conditional ruleset, while preserving default rules and hidden
information. Then repeat fresh full seat blocks. Policy tuning should wait
for a benchmark with substantially complete games; current evidence cannot
identify an external-loss mechanism without selection bias.
A trained value or policy prior is a plausible later policy experiment; these
results do not establish that it would improve Search at equal compute.

## Validation

See `validation.json` and `replay-validation.json`: formatting, strict release
workspace/all-target/all-feature Clippy, release locked workspace tests,
Python harness tests, 2,325 canonical replays and 602 native replays. Native
paired fixtures are checked for exact equality within every setup block. The privacy
regression checks equal external inputs from different real hidden worlds.
No default rule, engine version, card data or playing-policy source changed.
