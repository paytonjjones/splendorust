# Playing-strength research

Start revision: `4448c19`. The original `search` policy remains available.
`search128` and `search512` freeze its depth-eight, width-six, Strong-rollout,
Engine-leaf configuration at their named simulation count. `learned128` freezes
the E24 learned-cycle control at 128 simulations. Candidate `--iterations` and
`--depth` do not change these controls.

## Evidence and status

- E23: 32-feature logistic leaf. Strong outcome training. Large internal gain,
  but 19/2,000 development games capped. Not promoted.
- E24: same checkpoint plus observation-history cycle escape. Fresh confirmation
  earned 79.30% conditional credit against Search128; 19,999/20,000 complete.
  Conservative 95% interval [78.33%,80.27%] includes the missing outcome. The
  existing strict promotion gate rejected the one incomplete game. Its decision
  remains intact. This is the current stronger research control.
- E25: 79,044-parameter residual policy/value network and observation-keyed PUCT.
  Outcome-only value learning and one-action policy distillation failed the first
  playing screen. The checkpoint and ablations are preserved.
- E26: enhanced features, residual correction to the logistic value, and teacher
  root-value / soft-policy targets. In development; no final claim yet.

See `EXPERIMENTS.md` for hypotheses recorded before implementation and seed
reservations. Per-experiment folders contain raw reports, checkpoints, training
metrics, manifests, inference parity results, logs and failure evidence.

## Models and algorithms

E25 encodes 290 float32 inputs: relative player resources/progress, reservation
slots with opponent blind IDs masked, market card descriptors, bank, deck sizes,
player count, current-player flag, final-round flag and available nobles.
E26 appends E23's 32 relative progress and affordability features. Both use a
128-unit ReLU stem, a two-layer residual block, a 67-logit policy head and a
scalar value head. E26 adds the E23 logit to the learned value correction.
Main action IDs encode distinct-color takes (0–31), double takes (32–36), visible
reservations (37–48), blind reservations (49–51), visible buys (52–63), and reserved
buys (64–66). Legal masks exclude impossible IDs.

Native inference uses Rust float32 dense layers. PyTorch is used only in the
isolated training environment. Binary weights are included in the source
fingerprint. No inference dependency or allocation was added to splendor-core.

PUCT shares nodes within one real decision, keyed by the exact actor observation
with only the turn counter removed. It samples a fresh hidden world each
simulation. It does not retain the tree across real decisions. Q values belong
to the actor at each node; terminal shared wins retain fractional credit.
Unfinished simulations use a heuristic value, never a declared game outcome.
Payments, returns and noble choices use the existing heuristic. All canonical
legal choices remain in the core. Real repeated main positions can restrict
search to legal purchases, as in E24. The neural models are two-player models;
the tree agent uses Strong for other player counts, not an untested neural claim.

## Reproduction

The Python environment used PyTorch 2.5.1 and NumPy 1.26.4 with Apple MPS.
Training seeds and dependency versions are recorded in model manifests. MPS
bitwise reproducibility is not guaranteed. E23 training uses NumPy 2.4.3.

```
cargo build --release --locked --example neural_data --example neural_data_v2
# E25 independent setup and policy streams:
target/release/examples/neural_data 12000 250000000 950000007 128 learned-cycle local/research/neural-train.bin
target/release/examples/neural_data 2000 260000000 960000007 128 learned-cycle local/research/neural-dev.bin
python research/train_neural.py local/research/neural-train.bin local/research/neural-dev.bin research/e25/model --epochs 20
# E26 uses fresh setup streams and teacher search targets:
target/release/examples/neural_data_v2 12000 280000000 980000007 128 learned-cycle local/research/neural-v2-train.bin
target/release/examples/neural_data_v2 2000 290000000 990000007 128 learned-cycle local/research/neural-v2-dev.bin
python research/train_neural_v2.py local/research/neural-v2-train.bin local/research/neural-v2-dev.bin research/e26/model --epochs 30
```

The large raw training files stay under ignored `local/research/`; their hashes
are in manifests. They have not been deleted. Binary schemas are recorded in
data-generation manifests. Every setup stays within one split. Setup IDs are
used only for grouping and leak checks, never as model features. E25 masks
missing outcome labels. E26 can use an observation-only teacher target without
an outcome; it never calls that target an actual game result.

Development may proceed with incomplete games under the user-approved rule in
EXPERIMENTS.md. Retain all requested outcomes and their conservative bounds.
Final confirmation remains separate from training and development. No claim of
best-in-class or SOTA performance has been established.
