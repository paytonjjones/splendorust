# AlphaZero on its own rules

This profile adapts **SplendoRust**, not AlphaZero. The referee is the unchanged
[pinned public source](https://github.com/lyquentxy/splendor/tree/32a27ac1f85d5de2766cc5f60c2bf04e557f7836).
Its pretrained two-player checkpoint, network, MCTS, legal generator,
transitions, rewards and search settings are unchanged. The existing canonical
comparison in `../REPORT.md` and `../results/` remains diagnostic evidence.

Canonical published Splendor remains the default. Its core and engine version
are unchanged. The learning loop, data and confirmed E56 weights are unchanged.

## Reusable boundary

`Environment` specifies observations, sampled states, legal actions,
transitions, model-action indices and terminal
rewards. `PolicyValue` is a separate evaluation and policy interface. `NeuralAgent` uses one
PUCT expansion/selection/backpropagation kernel for both environments. The
canonical adapters call the existing core, encoder, safe choices and subphase
heuristics. Its normal root history/cycle policy and public API stay unchanged.
The native adapter offers all native actions without a canonical-action filter.

`native_environment.rs` is an independent Rust implementation of the pinned
native rules for search simulations. It is not the benchmark referee. The real
benchmark applies every chosen action through upstream `getNextState` and
checks terminal rewards through upstream `getGameEnded`.

Both profiles use the same frozen SplendoRust model. The native translator uses
the existing 392-feature contract, 81 policy outputs and two value outputs.
Market/reservation positions map directly. Native noble slots are kept for rule
checks, then sorted by noble ID in SplendoRust model input, as in its canonical
encoder. No weight, network architecture, loss or search coefficient changes.
The `same_model_feature_contract` test checks this normalization on 64 setups.
Native standalone returns and pass use the model's existing outputs 60–80.
The canonical encoder's original 67-action projection remains unchanged.

## Exact native rules

| Native IDs | Behavior |
|---|---|
| 0–11 | Buy the corresponding visible market slot. Use colored tokens first, then required gold. Refill the slot if that tier has cards. |
| 12–23 | Reserve the corresponding visible slot if fewer than three cards are reserved. Refill it. |
| 24–26 | Reserve a hidden card from the selected nonempty tier, with the same reservation cap. |
| 27–29 | Buy a reserved slot with colored-first payment. Shift later reservations forward. |
| 30–54 | Take the upstream combinations of one, two or three different colors. Small takes stay legal when more colors are available. The resulting hand must contain at most ten tokens. |
| 55–59 | Take two of one color if the bank has at least four, with the same hand cap. |
| 60–74 | Return one or two different colored tokens. This is a full turn, even below ten tokens. |
| 75–79 | Return two of one colored token. This is a full turn. Gold is not returned by these actions. |
| 80 | Pass is always legal in a nonterminal native game. |

Reserve gold is granted only when gold remains and the pre-reserve hand has at
most nine tokens. At ten tokens, no gold is granted. There is no take-and-return
compound action and no separate payment phase. Each native action finishes one
turn. The purchase transition claims **all** eligible nobles. Take, reserve,
return and pass do not claim nobles. These are intentional native differences.

The native referee checks termination only after an even number of turns.
It ends when the best score reaches 15 or the clock reaches 124. Prestige breaks
rank first; fewer purchased cards breaks a prestige tie. The native signed
rewards are +1/-1 for a sole winner and +0.01/+0.01 for a shared win. Search maps
these signed rewards to (reward+1)/2, which is the model value scale. Benchmark
win credit instead gives 1 to a sole winner or 0.5 to each shared winner.
Native score-cap wins are legitimate native outcomes and are labeled separately.
They do not establish a result under canonical rules. No artificial pass,
canonical fallback, early unsupported stop or new stalemate winner is used.

The Rust simulator samples native chance draws uniformly from the remaining
cards in the chosen tier, as upstream random_seed=0 does. A validation-only
fixture entry point also implements upstream's nonzero seeded draw selector
for exact differential branch tests. It is gated by `environment-validation`.
The policy worker has no fixture operation and rejects extra observation fields.

## Information and RNG

SplendoRust receives only public bank/market information, public purchases,
bonuses/scores/noble ownership, deck counts, reservation tiers/visibility, and
its own private reservation identities. A remembered public reservation stays
known. Opponent blind IDs are 255. The observation schema has no setup seed,
referee RNG, native deck mask or future order. It rejects an opponent blind ID.
The root legal set is independently regenerated from this public observation.

Each search determinization assigns unknown cards without replacement within
their tiers. It must reproduce the input observation exactly. Native network
input is built from such a sampled partition, not from the actual referee state.
There are three sampled root worlds, as in the confirmed champion configuration.
Each leaf encoding also uses observation-only sampling, as the canonical model
path does. No hidden fixture is sent to the policy process.

**Information asymmetry:** unchanged AlphaZero receives the native board, which
contains true unordered remaining-card membership and both players' private
reservation identities. SplendoRust does not receive those fields. AlphaZero's
native state has an unordered deck and samples refills; there is no stored future
deck sequence. This benchmark measures the agents with this declared asymmetry.
It is not an equal-information comparison.

`stream(master,label,block,identity)` is the first 64 bits, little endian, of
SHA256 of `native-v1:{master}:{label}:{block}:{identity}`. Labels are `setup`,
`policy` and `chance`. Policy identity 0 is SplendoRust; 1 is AlphaZero. Setup and
referee NumPy/Numba streams use the low 32 bits. SplendoRust uses its 64-bit RNG;
AlphaZero's seeded NumPy/Python/Torch RNGs and unchanged chance universes stay
separate. A setup is constructed once and copied for both seats. The chance seed
for each completed turn is shared across rotations. This pairing does not force
different actions to draw the same card.

The unchanged upstream `pit.py` selection call uses argmax of MCTS policy,
temperature 0.5 for the first six total turns and zero thereafter, full search,
800 simulations, cpuct 0.8, fpu 0.0593, three universes, no forced playouts and
normal memory cleanup. Seeds make the unchanged stochastic code reproducible.

## Run and verify

Use the pinned Rust toolchain, Cargo.lock, CPython 3.11.13 and
`../requirements.txt`. The existing setup command fetches the pinned sources and
creates the inference environment; do not rewrite its diagnostic manifests.
If sources already exist in another worktree, the ignored local directory can
point to those clean sources and the pinned inference environment.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --release --locked --all-features
cargo build --release --locked --all-features -p splendor-arena \
  --example native_policy_worker --example native_rules_probe \
  --example strength_worker --example strength_replay
local/strength/inference/bin/python -m unittest discover \
  -s benchmarks/strength/native -p 'test_native.py' -v
local/strength/inference/bin/python benchmarks/strength/native/validate.py \
  --games 100 --output NEW-differential.json
local/strength/inference/bin/python benchmarks/strength/native/schedule.py \
  --games 2000 --master 4110000000 --workers 8 --output NEW-screen
local/strength/inference/bin/python benchmarks/strength/native/replay.py \
  NEW-screen/games.jsonl --output NEW-screen/replay.json
local/strength/inference/bin/python benchmarks/strength/native/summarize.py \
  NEW-screen/games.jsonl --output NEW-screen/summary.json
```

`canonical_parity.py` compares every canonical choice and state with a release
worker built from base revision d9d4e4d. Build that immutable reference under
`local/strength/baseline/target`; do not replace the main checkout.
`scaling.py` compares the same 128-game schedule at 1/4/8 processes and requires
identical actions/state digests/work counts. Its times include lazy compilation,
worker startup and RPC. The benchmark separates fixed simulation budgets from
wall-time or equal-compute claims. Raw shards retain every command and hash.

The milestone uses fresh master 4120000000 and 20,000 games. Settings are frozen
before the screen. All schedules use full seat rotation, and missing outcomes
retain [0,1] credit bounds. Confidence intervals resample independent setup
blocks. A separate Hoeffding interval gives a conservative distribution-free
bound under the independent-block sampling assumption. No incomplete game is
converted into a victory. Every saved game must pass the native replay check.

Completed histories are also stored as deterministic lossless `.jsonl.gz`
archives to keep large raw records out of Git. `archive-index.json` records both
compressed and exact uncompressed SHA256 hashes. Before using the commands above
on an archived result, restore its raw file:

```sh
gzip -dc confirmation/games.jsonl.gz > confirmation/games.jsonl
```

The original raw files remain in the execution worktree. Their ignored status
does not remove them. Shard logs, plans, metadata, model/source hashes, summaries
and replay evidence remain beside the archives. `archive.py` verifies every
archive by decompression before it writes the index.
