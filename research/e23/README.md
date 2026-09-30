# Learned value experiment

The baseline is commit `4448c19`. Search is unchanged. The initial two-player
model is logistic regression without an intercept, with 32 float64 weights.
It uses 16 own-minus-opponent features and those differences multiplied by
maximum player prestige / 15. The features are prestige, purchased-card count,
capped bonuses, total tokens, gold, best noble proximity, reservation count,
current-player flag, three tier-specific best card values, three tier-specific
affordable fractions, best points per missing token, and prestige >= 12.
Card values use the visible market only. Private and public reservations are
excluded from affordability features for this first model. All features accept
Observation only. Multiplayer inference normalizes pairwise odds; multiplayer
strength must be tested separately before any claim.

The generator records both seats at main phases on turns congruent to 0 or 1
modulo 4. It uses independent setup and policy RNG streams. All positions from
one setup stay in one file/split. Completed games supply fractional win credit;
blocked and capped games supply no labels and have explicit manifest counts.
The cap for data generation is 2,000 decisions, not a declared game outcome.
This creates completion selection bias which the playing-strength screens must
check. Training is deterministic full-batch Newton logistic regression with
L2 coefficient 0.0001 and no hyperparameter selection on the development set.

```
cargo build --release --locked --example value_data
target/release/examples/value_data 20000 210000000 strong local/research/train.jsonl 910000007
target/release/examples/value_data 4000 220000000 strong local/research/dev.jsonl 920000007
local/research-venv/bin/python research/train_value.py local/research/train.jsonl local/research/dev.jsonl research/e23/model.json
```

Python training requires only NumPy 2.4.3. It is isolated from the Rust engine.
Model JSON records dataset hashes and held-out prediction scores. Initial timing
controls ran on a shared host while an example was being built, so their timing
is descriptive. Repeat isolated timing before a fixed-compute claim.
