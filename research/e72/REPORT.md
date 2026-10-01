# Gumbel planning adaptation

Replace the optional research search operator with Gumbel root selection,
sequential halving over up to16 candidates, completed-Q policy labels and
improved-policy allocation inside the tree. Mixed-value completion uses visited
prior-weighted action values and the network value. Use normalized completed
values, c_visit50 and c_scale0.1. Evaluation noise is0; teacher noise is1.
This is a native Rust adaptation with three sampled worlds and fixed budgets.
It does not reproduce a perfect-information guarantee or establish a rank.

Sources: [Danihelka et al., ICLR2022](https://openreview.net/forum?id=bERaNdoegnO),
[DeepMind mctx Q transforms](https://github.com/google-deepmind/mctx/blob/main/mctx/_src/qtransforms.py),
[interior selection](https://github.com/google-deepmind/mctx/blob/main/mctx/_src/action_selection.py).
Our halving schedule divides each remaining phase budget across active actions,
with at most one extra visit per action; it uses exact total fixed budget.

Old names and behavior remain available. New names: flywheel-gumbel (noise0),
flywheel-gumbel-noisy (noise1). Both load SPLENDOR_BEST_MODEL. The collector and
runner accept explicit actor and teacher agent names, with separate budgets.

Validation:105 release workspace tests and strict workspace Clippy passed.
Python:64 tests,35 passed,29 optional-reference skips. Tests cover completed
values, equal-Q prior identity, accurate-Q improvement, exact budgets0..128,
legal normalized targets and seed identity. Legacy934 raw rows remain byte
exact. A noisy800 teacher leaves all910 student actor states unchanged; labels
change and are legal. Serial/parallel output is byte exact.

On568 fixed Strong observations, median cost at128 was5.664ms for the old
search and5.760ms for Gumbel (ratio1.0169). Same E68 model and depth16;
shared-host timings, three alternating repeats. Cost source compiled directly
against the recorded library build, without changing arena source mid-run.
Initial parse/borrow and test variant-name errors are preserved and corrected.
