# WebGPU browser experiment

Hypothesis: the frozen champion weights can use FP32 WebGPU inference with
Rust observation encoding and PUCT search. Faster inference can fit more
search into a 10-second limit for the full bot turn. Keep 6,400 simulations
as a ceiling. Keep the core rules and all legal choices unchanged.

Budget: four hours elapsed, one owner, one GPU job at a time. First export a
static ONNX graph from the hash-checked native weights. Compare outputs on
fixed public inputs against the portable Rust model. Maximum absolute error
must be at most 0.001 for policy logits and 0.0001 for values. Record tighter
observed errors. Measure warm, batch-one GPU inference, including readback.
Then connect the existing Rust search to a separate GPU worker with shared
memory. Test real turns, a full-turn deadline, responsive UI, device failure,
and the production build. Keep Actions disabled and the README unchanged.

This is a runtime experiment, not a new strength promotion. A time cap that
reduces the search count has unmeasured strength. Do not claim the native
research win rate for browser rules or the new numerical backend. Record
failed or unsupported tests. Do not deploy until the runtime checks pass.
