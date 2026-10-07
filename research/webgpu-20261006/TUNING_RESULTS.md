# Time levels, fallback, and GPU cost

The page offers 5, 10, and 30 second maximum turn times. The default is 10 seconds. A new game uses the selected level. Retry retains the original level. Logs keep the actual model, inference backend, and limit for each game.

Without a WebGPU adapter or worker isolation, a new game uses E81 through CPU WASM. Its registered ceiling remains 128 simulations. The page identifies this smaller engine. A running GPU game does not switch models after a device error.

The page shows elapsed engine time and the current game limit. Loading shows the active engine, the download stage, and progress from received bytes. GPU preparation uses an indeterminate bar. No estimated progress is presented as measured progress.

## Accepted changes

The GPU path keeps a fixed GPU input buffer, captures the graph, and copies both outputs into one readback buffer. Every tested output meets the original FP32 tolerance: 0.001 for logits and 0.0001 for values. Both output tensors are disposed after each call. The frozen source weights and batch-one ONNX graph hashes are unchanged.

The older capture failure used a different input and output path. It remains in RESULTS.md. This change passed all 17 public positions and 500 repeated calls with changing inputs and output disposal. See tuning-capture-disposed.json.

Four sequential 500-call runs compared the old and new paths. The old median times were 2.640 and 2.355 ms. The new times were 1.975 and 1.970 ms. The mean of those medians fell by 21%. These are inference measurements, including input transfer and CPU readback, not playing-strength results. No other owned GPU job ran during these four measurements. See tuning-paired-profile.json.

A GPU game also skips the duplicate 19,123,540 byte native model download. The GPU graph has its own checked hash and frozen source hash. The original native binary remains published as an open weight asset. CPU games download only the 569,624 byte E81 model.

## Native comparison and batching

The same frozen weights and public token fixtures ran through native FP32 MPS. Each measured call includes input transfer and CPU output readback. Public tokenization and service queue time are excluded. The final run used 500 calls per batch size with no other owned GPU job. See native-profile.json and profile_native.py.

| Inference path | Positions per call | Median call time | Positions/s |
| --- | ---: | ---: | ---: |
| Native MPS | 1 | 4.021 ms | 249 |
| Native MPS | 32 | 4.466 ms | 7,165 |
| WebGPU | 1 | 2.220 ms | 450 |
| WebGPU | 4 | 2.205 ms | 1,814 |
| WebGPU | 8 | 2.645 ms | 3,025 |

The native research service batches positions from concurrent games. At commit `c9c932b`, the browser search requested one position at a time. This makes native throughput per position much higher than native single-position latency. In these matched single-position measurements, WebGPU is faster than MPS.

Batches of eight give about six times the WebGPU throughput of batch one. This is an inference-only result. A single-game search must collect multiple leaf positions before inference can use it. Virtual visits or a leaf queue change search order. That needs a separate candidate and fresh strength evaluation. At that measurement, batched search was not deployed and both larger graphs were development probe assets. Commit `762289d` later deployed batch-eight search. See [the direct browser comparison](../browser-batch-20261006/PLAN.json). Reproduce them with `web/scripts/export-webgpu.py --batch-size 4` or `--batch-size 8`, then run the development probe with `batch4` or `batch8`.

The timeout bot has no fresh playing-strength result. More simulations are a possible benefit, not a verified strength gain.

## Validation

Format, strict release workspace Clippy, default and all-feature release workspace tests, TypeScript, and both builds passed. All 14 browser tests passed. They cover time levels, the visible timer, real download progress, E81 fallback, device loss, recording, and native replay. The log backend passed 37 checks. The GPU mailbox passed its forced race and 100,000 round trips. See TUNING_VALIDATION.json. The public deployment check is recorded separately after deployment.

The public deployment of `c9c932b` completed one normal UI game. All 23 engine turns stayed below 10 seconds (maximum 9902.645 ms). Both downloads reported their complete byte counts. All 21 uploads succeeded. The private replay passed native validation: one verified, zero rejected, one finished. All 16 checked public asset hashes match the final build. This checks runtime behavior, not playing strength. See tuning-public-check.json and tuning-public-assets.json.
