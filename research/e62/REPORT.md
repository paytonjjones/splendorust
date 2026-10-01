# E62: fixed-base residual model validation

Add a trainable 512-input RMSNorm/SwiGLU correction branch to frozen E59.
The branch has width 192, three blocks, and zero-initialized output heads.
Policy corrections add to base logits. Value corrections add before tanh.
The model has 591,193 parameters; 448,787 are trainable.

The initial Python function equals E59 exactly on 64 positions sampled across
held-out games. Three optimizer updates change the correction branch but leave
all base parameters and normalization buffers unchanged. Base native export
matches the E59 model hash exactly. Checkpoint reload preserves outputs exactly.
Python/native maximum masked-policy/value error is below 0.000002 both before
and after updates. Rust tests check initial identity, nonzero corrections,
reference inference, malformed sizes, truncation, and nonfinite payloads.
Eight complete games pass action and invariant checks. These games establish
execution validity; they are not a strength assessment.

All 102 release workspace tests and strict Clippy pass. Python checks pass;
29 optional external-reference checks are skipped. Full logs, fixtures, previous
source versions, and the verification script are saved here. Runtime uses Rust;
PyTorch remains an offline training tool. No engine rules or replay semantics
change. E63 measures training gain and decision cost separately.
