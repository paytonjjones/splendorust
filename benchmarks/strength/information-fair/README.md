# Information fairness in the native AlphaZero comparison

This benchmark changes information only. It uses the same E81 Gumbel128
endpoint as E92 and the unchanged AlphaZero800 endpoint. The actual referee
is the pinned upstream native engine. The original native and canonical
benchmark files are unchanged.

| Arm | SplendoRust input | AlphaZero input |
|---|---|---|
| `control` | Public state, own private cards, public reservation memory | True unordered card partition |
| `blind-alpha` | Same as control | Sampled partition from public state and own private cards |
| `privileged-sr` | True unordered card partition | Same as control |

The blind input comes from the existing public native worker's `sample`
operation. This operation rejects opponent blind IDs and extra fields.
It assigns unknown reservations and remaining tier cards jointly, without
replacement. It returns the 56-by-7 native board in actor-relative order.
This board has hypothetical hidden cards. It cannot reveal the real hidden
assignment. Known reservations, purchased cards, own reservations, bank,
token/bonus totals, nobles, clock and deck counts are preserved. If public
information determines a card uniquely, the player can still infer it.
A separate `information` seed stream selects the sampled partition for each
real turn. It does not consume AlphaZero or referee RNG. The three upstream
chance universes, model, weights, MCTS, selection and memory cleanup remain
unchanged. This is one public-consistent root sample per decision; it is not
a new belief-search algorithm. No claim is made that the upstream network
uses every piece of public history optimally.

The privileged path requires the explicit `information-benchmark` Cargo
feature and the separate `privileged_native_worker`. Its input consists of
full reservations plus unordered deck sets. Validation checks the complete
90-card partition and rejects duplicate, absent or wrong-tier cards, seeds
and deck-order fields. List order has no effect. Root sampling copies the
known partition. Each simulated transition uses the normal native draw
sampler. Every neural leaf uses that exact simulated partition, including
both actors' reservations. Model weights, feature contract, search kernel,
coefficients, iterations, depth and world-pool count are unchanged. Three
root worlds can be identical because the partition is known. Privilege is
not added to canonical or default public policies.

[PREREGISTRATION.md](PREREGISTRATION.md) fixes the hypotheses, seeds, budgets
and contrasts before outcome runs. `freeze.json` records source, binaries,
models and the upstream checkout. Each schedule stores exact commands and
raw histories. `replay.py` checks every legal move, chance seed, state hash,
reward, paired setup and information-input hash. For the blind arm it
reconstructs every sampled input. For the privileged arm it checks exact
partition hashes. Replay does not rerun policy search.

Build and test with the pinned toolchain and existing pinned inference
Python environment:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --release --locked --all-features
cargo test --workspace --release --locked
cargo build --release --locked --all-features -p splendor-arena \
  --example native_policy_worker --example privileged_native_worker \
  --example native_rules_probe --example strength_worker
local/strength/inference/bin/python -m unittest discover \
  -s benchmarks/strength/information-fair -p 'test_*.py' -v
```

The worker-parity test requires an immutable main worker built from base
`2f627b0` under `local/strength/control-source/target`. Archive that revision's
Cargo files, toolchain file and crates into the directory and build its
`native_policy_worker` in release mode. The existing strength setup process
supplies the pinned clean external checkout and Python environment.

To reproduce one arm in a new directory:

```sh
local/strength/inference/bin/python benchmarks/strength/information-fair/schedule.py \
  --arm blind-alpha --games 20000 --master 4910000000 --workers 8 \
  --iterations 128 --search gumbel --model research/e81/model/model.bin \
  --output local/strength/fair-reproduction/blind-alpha
```

Repeat for `control` and `privileged-sr` with the same master. Then replay each
`games.jsonl`, and pass their common parent directory to `summarize.py`.
Compressed raw archives can be read by `summarize.py`; decompress a copy for
`replay.py`. Both rotations and all three arms form a matched setup block.
Paired intervals resample whole blocks. Fractions of the control gap removed
are separate counterfactual estimates; they cannot be added. Native turn-cap
outcomes and unknown-outcome sensitivity are reported separately. These are
fixed-budget native-rule comparisons, not equal-compute or canonical rankings.
