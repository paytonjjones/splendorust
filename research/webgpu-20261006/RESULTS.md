# Browser WebGPU result

The frozen Entity champion runs with FP32 WebGPU inference. Rust still owns
observation encoding, legal choices, and PUCT search. One worker runs search;
a second worker runs GPU inference. The page can process input during search.

The whole bot turn has a 10-second budget. All decisions share a deadline at
9.9 seconds to leave time for choices and record updates. The simulation count
of 6,400 is a ceiling. Actual counts depend on the device and position.

## Local measurements

Apple M4 Pro, Chrome 154.0.8037.98, hardware Metal 3 adapter, no browser flags,
one GPU job at a time. Warm inference includes batch-one input and output
readback. Model loading is outside the turn measurement.

| Check | Result |
| --- | ---: |
| Public numerical fixtures | 17 |
| Maximum policy logit error versus portable Rust | 0.00001335144 |
| Maximum value error versus portable Rust | 0.00000102818 |
| Warm inference median | 2.80 ms |
| Warm inference p95 | 3.48 ms |
| Seed 91337, first reply | 4,100 simulations in 9.902 s |
| Seed 17798000007, bot starts | 4,062 simulations in 9.902 s |
| Seed 17798000019, bot starts | 4,088 simulations in 9.903 s |
| Longest main-thread timer gap during the first reply | 22.7 ms |

The retained numerical thresholds are 0.001 for logits and 0.0001 for values.
The original portable WASM decision took 417.8 seconds with 6,400 simulations;
see [the CPU receipt](../browser-champion-20261006/browser.json).
These latency checks are specific to this host. They are not a strength test.
The browser uses canonical rules; the native research chance-universe behavior
is not part of this change. No new research champion is promoted.

## Failed branches and checks

The first public full-game check found a handoff race after short tests passed.
The GPU worker read the mailbox state twice. A request arriving between those
reads could make it wait on state 1, although state 1 means work is ready.
Inference then timed out. The fix reads state once and waits only on the old
idle/completed state. A regression test forces that interleaving and also
checks 100,000 real worker handoffs without GPU arithmetic. Keep
[the failed public receipt](failed-public-handoff.json).

Graph capture with reusable external GPU buffers failed numerical comparison.
The first recorded error was 13.64 for logits and 0.6442 for values. Additional
warmup did not repair it. The selected path disables graph capture. Keep
[the failed receipt](probe-capture-cold.json) separate from [the final probe](probe.json).

Worker script fault injection through network routes did not reach the worker
in this harness. A Chrome feature flag also did not remove its WebGPU API.
Those failure tests were rejected and replaced with direct worker API fault
injection. The final tests check missing WebGPU, real GPU device destruction,
a restart after device loss, three capped turns, and responsive page timers.
The preview applies the production content security policy.

Local checks passed: formatting, strict release workspace Clippy with all
features and targets, release workspace tests with default and all features,
TypeScript, both builds, five champion browser tests, six recording tests,
32 game-log backend checks, and the mailbox stress check. Recording tests include a complete game at a
smaller test budget and native replay validation. The fixed-budget native
6,400-simulation diagnostic was not repeated for this backend.

## Reproduce

Install the web lockfile and use the pinned Rust toolchain. Build the test site
with `npm --prefix web run build:test`. From `web/`, run
`npx playwright test tests/champion.spec.ts tests/recording.spec.ts --workers=1`.
Use a hardware WebGPU browser. Run one GPU test worker at a time.

For numerical fixtures, run
`cargo run --release --locked -p splendor-web --example webgpu_fixtures`.
Start the dev server, then from `web/` run
`node scripts/probe-webgpu.mjs http://127.0.0.1:5173`.
The exporter uses NumPy 1.26.4 and ONNX 1.17.0, reads the hash-checked native
weights, and exports FP32 operations without training.

[Export hashes](export.json), [runtime hashes](runtime.json), and the three
browser receipts in this directory identify the tested model and inputs.
## Public deployment

The corrected source commit is `7bd5e9d`. The deployment is
[3184d119](https://3184d119.splendorust.pages.dev), with the live site at
[SplendoRust](https://splendorust.pages.dev). All 12 public model, metadata,
runtime, JavaScript, and WASM assets matched the production build hashes.
See [the asset receipt](public-assets.json).

The normal public interface completed one game: 81 engine decisions and
52 player turns. No test bridge or seed override was used. All 26 bot turns
were at most 9,902.705 ms. Five late-game decisions reached 6,400 simulations;
the other main decisions stopped at the time cap. The initial model load took
8.62 seconds and is outside the per-turn budget. This host had no GPU fallback.

All 25 observed uploads returned 202. Public journal reads returned 405.
The downloaded record reported the production WebGPU backend and 10-second
budget. Native replay validation reported `verified=1 rejected=0 finished=1`.
The record hash is in [the public check](public-check.json). The private replay
stays in ignored `local/web-games/`; it is not published as a visitor dataset.
The game outcome is a runtime check, not a strength estimate.
