# Neural throughput on the shared M4 Pro

## Selected change

The experiment selected production commit **`03326dd230da44035a145db1e1dc531cd7152aef`**.
Current `main` already contains the equivalent patch as **`5d02e8c`**. The two
commits have the same stable Git patch ID; `5d02e8c` is the integration point
for this checkout.
It changes only native pointwise inference in `transfer.rs`. It packs weights
for four output channels once at model load. The Rust compiler uses ARM vector
FMA instructions. Each output keeps the original input-channel FMA order.
Weights, model architecture, activations, search, RNG, rules, and target definitions
stay the same. `Model::infer_original` retains the original deterministic path.

The fresh confirmation pair increased self-play throughput **60.5%**:
1,000 games fell from **39.22 s to 24.43 s**. Two 2,000-game candidate/incumbent
pairs increased arena throughput **65.2% and 81.3%**. CPU time fell about 38%.
All final self-play data bytes and ordered arena records match before and after.
This supports integration without a new strength promotion experiment.

These are **shared-host measurements**. The user requested that the separate
learned-strength chat continue. The results are conditional on this Mac, these
frozen models, and these budgets. They are not portable speed guarantees.

## Conditions and identities

- Date: 2026-09-30. Apple M4 Pro, 14 CPU cores (10 performance, 4 efficiency),
  48 GiB RAM. macOS 26.7, build 25G229.
- Isolated worktree `71dc`, branch `codex/neural-throughput`, base `3821a71`.
  The learned-strength checkout was not changed or paused.
- Pinned Rust 1.98.1 and Cargo.lock. Release build, thin LTO, one codegen unit.
- Two players, 128 simulations, depth 16. The flywheel's existing opening
  exploration, late-game fallback, seed rules, and seat rotations are unchanged.
- Frozen incumbent SHA-256:
  `d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600`.
- Frozen candidate SHA-256:
  `142f4bc78e84d2bcb0e437b0e0c86147f9b162bbd0bac7f716271aa55a9eab39`.
- Source fingerprints, verified from commit contents with the build script's
  path ordering and FNV calculation: base `02e8778089114225`, selected
  `1505ac8794c53416`. Full binary hashes are in
  [final-confirmation.json](results/final-confirmation.json).
- Frozen weights are copied to `incumbent.bin` and `candidate.bin`. No training
  or checkpoint modification took place. Accelerator frameworks are local
  research tools; the production commit adds no dependency.

Timing includes process/model startup, output, and the last unfinished batch.
Drivers use a monotonic clock and child user+system CPU accounting. Dividing CPU
seconds by wall seconds estimates occupied CPU cores. Process samples are in the
raw artifacts. Self-play positions mean saved Main-phase training rows. Arena
positions mean all action decisions, including mandatory phases. These counts
must not be compared as the same unit. Arena simulation counts are unavailable
in the existing record schema; no count is inferred from decision totals.

## Final end-to-end results

The final order was baseline, selected, selected, baseline. The first pair used
setup seed 2,500,000,000; the reverse pair used fresh seed 2,600,000,000. Self-play
policy seeds were setup seed + 3,000,000,000. Each arena run has 2,000 requested
and completed games. Each self-play run has 1,000 requested and completed games.
There were no blocked or capped games in these final runs.

| Seed | Workload | Build | Wall s | CPU s | CPU cores | Games/s | Positions/s | Simulations/s |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 2500000000 | selfplay | baseline* | 42.78 | 481.34 | 11.25 | 23.37 | 1315 | 168204 |
| 2500000000 | arena | baseline | 76.44 | 984.47 | 12.88 | 26.16 | 2164 | — |
| 2500000000 | selfplay | final | 24.46 | 298.46 | 12.20 | 40.88 | 2299 | 294175 |
| 2500000000 | arena | final | 46.28 | 602.60 | 13.02 | 43.21 | 3575 | — |
| 2600000000 | selfplay | final | 24.43 | 298.92 | 12.24 | 40.94 | 2304 | 294820 |
| 2600000000 | arena | final | 45.60 | 604.38 | 13.25 | 43.86 | 3634 | — |
| 2600000000 | selfplay | baseline | 39.22 | 478.14 | 12.19 | 25.50 | 1435 | 183655 |
| 2600000000 | arena | baseline | 82.68 | 968.31 | 11.71 | 24.19 | 2004 | — |

Arena simulation values shown as a dash mean **not measured**.

`*` The first baseline self-play overlapped a one-CPU native batch microbenchmark.
Its 74.9% paired throughput gain is **excluded** from the headline. It remains
valid parity evidence. Own builds, tests, scaling sweeps, and accelerator probes
were finished before the other final timings. External chat activity continued.
The first plan's blanket statement about own-job isolation is corrected in the
compact final manifest. Original plans and process samples remain preserved.

The fresh reverse pair saved 37.7% self-play wall time and 37.5% CPU time. It
performed exactly 7,202,048 simulations and 6,942,962 inference calls per build.
The two arena pairs saved 39.5% and 44.8% wall time. Variation in occupied cores
and external load prevents a tighter portable estimate. No confidence interval
is claimed from two varying-load pairs. Earlier 256-game pilots are retained;
they include overlapping builds/tests and are not the main evidence.

## Profiler evidence and scope

A five-second macOS `sample` capture at 1 ms intervals sampled the base arena
with four workers. Top-of-stack counts were:

| Function | Samples |
|---|---:|
| `transfer::Norm::apply` | 11,693 |
| `transfer::Dense::apply` | 1,390 |
| `transfer::Block::apply` | 276 |
| `NeuralAgent::simulate` | 143 |
| legal-action enumeration | 81 |
| observation determinization | 74 |
| encoder | 71 |
| small allocator/free frames | 70 / 61 |

These counts identify inference as the main sampled active work. They are not
exact wall percentages. Main-thread condition-variable waits are also present;
that thread waits for game workers. Its waits do not establish a hot shared
application lock. The profiled run's wall time is excluded because a prototype
build overlapped it. See [profile.json](results/profile.json) and the complete
[stack sample](results/raw/profile-arena.sample.txt.gz).

Initial isolated batch-1 inference took median 52.8 microseconds per call on
64 saved real observation rows. The paired kernel sweep below used 100,000
calls per cell, three repeats, and alternating original/selected order.
Search time excluding inference was not instrumented. The sampler and final
fixed-work CPU reduction provide evidence without subtracting unrelated
microbenchmark times from whole-game CPU time.

| Workers | Original median s | Selected median s | Original calls/s | Selected calls/s | Ratio |
|---:|---:|---:|---:|---:|---:|
| 1 | 5.305 | 3.093 | 18849 | 32329 | 1.715 |
| 4 | 1.373 | 0.818 | 72850 | 122269 | 1.678 |
| 8 | 0.708 | 0.424 | 141291 | 235922 | 1.670 |
| 12 | 0.588 | 0.348 | 170074 | 287638 | 1.691 |
| 14 | 0.568 | 0.333 | 176048 | 300677 | 1.708 |

This sweep used the pre-cleanup packed-kernel source fingerprint
`4dce51733616a920`; the selected arithmetic is the same. Its raw binary/source identity
is preserved in the logs. Final whole-game results use the exact production
commit. [inference.json](results/inference.json) retains all 177 measurements.

## Base CPU scaling

One serial sweep used the same 256 self-play games and 2,000 arena games at
each worker count. Seed streams were 2,200,000,000 / 5,200,000,000 for
self-play and 2,220,000,000 for arena. All five self-play byte hashes and all
five arena record hashes agree. All games completed.

| Workers | Self-play wall s | Games/s | Positions/s | Simulations/s | CPU cores | Arena wall s | Games/s | Decisions/s | CPU cores |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 163.47 | 1.57 | 88 | 11214 | 0.80 | 1293.96 | 1.55 | 128 | 0.73 |
| 4 | 26.58 | 9.63 | 539 | 68969 | 3.91 | 249.42 | 8.02 | 665 | 3.46 |
| 8 | 15.49 | 16.52 | 925 | 118323 | 7.15 | 105.43 | 18.97 | 1574 | 7.90 |
| 12 | 11.94 | 21.45 | 1201 | 153579 | 9.78 | 81.73 | 24.47 | 2030 | 11.47 |
| 14 | 11.09 | 23.09 | 1293 | 165357 | 10.95 | 83.53 | 23.94 | 1986 | 11.91 |

Scaling improves through eight workers and approaches a plateau at 12–14.
The 12-worker arena was 2% faster than 14 workers in this single sweep. This
small difference under changing load does not justify changing the default.
The one-worker results include heavy shared load and own pilot/build overlap;
the apparent superlinear gain is not a hardware scaling claim.

Worker CPU usage, separate process samples, and the 10P/4E CPU mix are consistent
with scheduling contention and slower added cores. Hardware cache-miss and
memory-bandwidth counters were not collected. Cache or bandwidth limits cannot
be identified as the cause from this evidence. The packed kernel keeps shared
weights read-only and uses local temporary buffers. It adds about 233 KiB of
packed weights per depth-one model. The original weights remain for reference.
No core transition allocation or new inference lock is introduced.

## Independent-game batch prototype

The `research-batching` Cargo feature is off by default. It queues a 392-float
encoded leaf tensor and a private reply channel. It does not receive a game
state, setup seed, deck order, observation object, or RNG. Each game search
blocks on its own single pending evaluation. It resumes the same sequential
search after its output arrives. It does not speculate within one tree.

Each loaded static model has its own queue. A 200-microsecond deadline flushes
partial batches. The final few active games therefore cannot deadlock while
waiting for a full batch. Native mode evaluates the batch rows in one dedicated
thread. External mode uses one persistent Python worker, binary pipe messages,
and weights loaded once. There are no runtime LLM calls.

`SPLENDOR_GAME_WINDOW=256` permits enough independent games for large batches.
The normal collector window remains 64. Requested batches 8/16/32/64/128/256
were measured for inference. Whole-game probes used 8, 64, and 256 to test the
small and large latency/occupancy regimes without a full grid of costly games.

## Native CPU versus Apple backends

The Python graph reads frozen native weights and preserves the bootstrap graph.
PyTorch 2.5.1 MPS executes on Metal. Core ML 9.0 uses an FP32 MLProgram with
batch range 1–256 and `CPU_AND_GPU`. Core ML operation placement was not
measured; this is a GPU-enabled configuration, not proof that every operation
ran on GPU. The Neural Engine was not selected. No quantization was used.

Each cell is the median of three runs, including host input and returned output.
MPS return-to-CPU synchronizes before timing ends. Models are warmed before the
microbenchmark. Native values below are a one-thread row loop, not the parallel
CPU kernel sweep. These measurements ran at different times under shared load;
use the whole-game table for the integration decision.

| Batch | Native ms / positions/s | Torch CPU ms / positions/s | MPS ms / positions/s | Core ML ms / positions/s |
|---:|---:|---:|---:|---:|
| 1 | 0.040 / 25187 | 0.214 / 4665 | 6.496 / 154 | 0.077 / 12969 |
| 8 | 0.350 / 22861 | 0.459 / 17445 | 6.561 / 1219 | 0.180 / 44365 |
| 16 | 0.633 / 25280 | 0.719 / 22267 | 6.065 / 2638 | 0.287 / 55695 |
| 32 | 1.352 / 23665 | 1.241 / 25786 | 6.139 / 5212 | 0.515 / 62133 |
| 64 | 2.956 / 21653 | 2.229 / 28714 | 10.905 / 5869 | 0.922 / 69433 |
| 128 | 6.157 / 20789 | 4.209 / 30412 | 7.416 / 17259 | 1.695 / 75530 |
| 256 | 10.813 / 23675 | 8.305 / 30825 | 8.268 / 30963 | 3.363 / 76125 |

Core ML improves its isolated throughput with batch size, reaching about
76,000 positions/s at 256. The direct parallel native kernel reached about
301,000 calls/s at 14 workers in its paired sweep. A central evaluator also
adds queue, IPC, and reply latency to every dependent leaf.

Whole-game probes used seed 2,480,000,000, policy seed 5,480,000,000,
128 simulations, and depth 16. All requested games completed. Different game
counts in the small probes make their startup/tail cost more visible; they are
not paired speed estimates. The two 256-game accelerator probes share the
direct run's full seed prefix.

| Backend | Batch / workers / games | Wall s | Games/s | Positions/s | Simulations/s | Data byte parity |
|---|---|---:|---:|---:|---:|---|
| direct | 0 / 14 / 256 | 7.10 | 36.08 | 2025 | 259155 | exact |
| native | 8 / 14 / 16 | 6.35 | 2.52 | 144 | 18468 | exact |
| native | 64 / 64 / 64 | 15.01 | 4.26 | 238 | 30419 | exact |
| coreml | 64 / 64 / 64 | 11.48 | 5.57 | 311 | 39811 | different |
| coreml | 256 / 256 / 256 | 35.70 | 7.17 | 403 | 51544 | different |
| mps | 256 / 256 / 256 | 69.32 | 3.69 | 207 | 26540 | different |

The 256-game Core ML queue took 5.0 times the direct native wall time; MPS took
9.8 times. Both are rejected for production. The single-thread native queue is
also rejected: it preserves data but gives up native parallel inference.
These results reject these implementations and this small model on this host;
they do not prove that all Metal or native Core ML integrations must be slower.

Large batches did fill. Early occupancy reached about 255.8 at requested 256.
The last progress event averaged 221.8 because games finished at different
times. Mean occupancy at requested 64 was about 55.1; native batch 8 averaged
6.2. Full startup and tail costs are included in wall time. Progress counters
sample every 1,000 batches, so they do not include the final tail event.

## Correctness and semantic limits

Production tests compare all 81 policy logits and two values by `f32::to_bits`.
The production unit test covers more than 1,000 real observations, an upstream
model, a nonzero depth-three model, and gated dispatch. The extended integration
test adds the frozen incumbent and actual E47/E46 checkpoints. Exact data parity
also covers opening exploration, visit targets, teacher values, sampled hidden
inputs, and game outcomes across complete neural games. The four final arena
runs preserve ordered per-game records, including trajectory hashes. Fingerprint
and timing metadata are allowed to differ. ENGINE_VERSION does not change:
there is no change to rules, action enumeration, RNG, or replay semantics.

Final parity hashes, equal for both builds:

| Seed | Self-play data SHA-256 | Arena records SHA-256 |
|---|---|---|
| 2500000000 | `d438af00a2cb1ecab5b7c70807ec898ef44f574df132f993a0d6be6595431d55` | `315895b9b6129234a180092716e8b09c6d2a47020d5a4e5611e55b118ed69383` |
| 2600000000 | `2a1bd274c23236b8f4623f37dd4e1a27766178e4093b4c852e9bc451adbef3ad` | `6dbc905d5a48b1057e57897bd530f159609d64235989ff9093f01db55e7dbd34` |

Record hashes use canonical JSON: sorted keys, compact separators, ordered
records. Data hashes use raw uncompressed bytes. Scripts perform these checks.

Native queued batches 8 and 64 match their direct seed prefixes byte for byte.
Thus cross-game scheduling did not change the per-game RNG stream or labels in
these probes. Apple outputs satisfy `atol=1e-4, rtol=1e-5` on 64 real inputs and
each measured batch shape; maximum leaf-output error was 7.63e-6. This tolerance
is insufficient to preserve complete search behavior. Small rounding differences
can change near-tied choices. A different expanded node then changes how many
random samples that individual search consumes. No shared RNG causes this.

The bounded public Main-observation sequence diagnostic found agreement for
60/64 Core ML games, 238/256 Core ML games, and 241/256 MPS games. Among games
with matching public sequences, identical visit targets occurred for 58, 233,
and 236 games. Teacher values also differed, up to 0.0561 for Core ML and 0.1035
for MPS. The diagnostic excludes sampled blind reservations and deck availability,
and stops below turn 124. It is not a full action-history parity test.

The accelerator prototype keeps the target definitions and search algorithm,
but its generated labels and some trajectories differ numerically. Statistical
policy/strength equivalence was not established. Therefore it is not a valid
replacement for this task. Only the exact CPU kernel is selected. No incomplete
result is converted to a win. The earlier pilot with one incomplete arena game
retains that status and is not used for a strength claim or promotion.

## Rejected experiments and validation

P1/P1b padded seven spatial lanes to eight. Output parity passed, but timing did
not establish a reliable improvement. A compiler can discard an unused lane.
Keeping the eighth lane active did not produce a supported whole-game win.
The prototype snapshot, hypotheses, and timing logs are preserved. P3 instead
uses four real independent output channels and produced the measured gain.
The saved assembly contains `fmla.4s` for the packed accumulation.

Required checks passed: `cargo fmt --all --check`, strict release workspace
all-target Clippy with Cargo.lock, and release workspace tests. The worktree
suite has 101 passing tests, including the extended integration test. Feature
build Clippy and release tests also passed. Logs are in `results/raw` and hashes
are in `validation.json` / `local-artifacts.json`. Initial tool setup failures
(missing Torch in the first environment, missing Core ML dependencies) and
Clippy repairs are preserved. They are not benchmark successes.

## Integration and reproduction

For a checkout that does not already contain the equivalent patch, take **only**:

```sh
git cherry-pick 03326dd230da44035a145db1e1dc531cd7152aef
cargo fmt --all --check
CARGO_BUILD_JOBS=2 cargo clippy --workspace --all-targets --release --locked -- -D warnings
CARGO_BUILD_JOBS=2 cargo test --workspace --release --locked
```

On current `main`, do not cherry-pick the historical commit again. Verify that
`5d02e8c` is present and use the report and evidence in this directory.

Commit `9bd5d44` retains optional prototype code, parity fixtures, and scripts.
The final documentation commit retains reports and evidence. They are not needed for production. The CPU optimization applies to
bootstrap models at each supported depth; gated inference follows its existing
path. It keeps current allocations and adds a small read-only weight cache.
No sweeping rewrite was necessary after profiling established this simple win.

To reproduce in a fresh worktree of this complete research branch, build the
base and production commits in separate clean checkouts with the same pinned
settings. Place their release targets at `local/throughput/baseline/release`
and `local/throughput/final/release`. Build `splendor` and `flywheel_data`:

```sh
CARGO_BUILD_JOBS=2 cargo build --release --locked -p splendor-arena --bin splendor --example flywheel_data
python3 research/throughput/scaling.py --build local/throughput/baseline --output local/throughput/scaling-repeat
python3 research/throughput/final_confirmation.py
```

`final_confirmation.py` requires a new `local/throughput/final-confirmation`
directory and checks parity before storing each result. Retain existing evidence
and use a fresh checkout rather than overwrite it. The plan records model/binary
hashes and each complete command. The original production build also included
benchmark examples present as untracked tools; these do not enter the production
source fingerprint. The selected commit has no benchmark-tool requirement.

For inference tools on this complete branch:

```sh
CARGO_BUILD_JOBS=2 cargo build --release --locked -p splendor-arena --examples
cargo run --release --locked -p splendor-arena --example transfer_throughput -- research/throughput/incumbent.bin research/throughput/inputs.json
cargo run --release --locked -p splendor-arena --example transfer_batch_latency -- research/throughput/incumbent.bin research/throughput/inputs.json
```

These commands use Cargo's current target directory.
The saved `inputs.json` fixture was identified against the original reference:
all original 83-output vectors match exactly for that input set.

For accelerator experiments, use a local Python 3.11 environment with
`numpy`, `torch==2.5.1`, and `coremltools==9.0` plus its dependencies. The measured
Python executable was in the separate learned-strength environment; it was used
read-only. Core ML dependencies were installed under this worktree's ignored
`local/throughput/coreml-deps`. No shared environment was changed. With that
Python executable assigned to `PYTHON_BIN`:

```sh
"$PYTHON_BIN" research/throughput/accelerator.py --device mps --model research/throughput/incumbent.bin --inputs research/throughput/inputs.json --reference research/throughput/results/native-reference.json
"$PYTHON_BIN" research/throughput/accelerator.py --device coreml --model research/throughput/incumbent.bin --inputs research/throughput/inputs.json --reference research/throughput/results/native-reference.json
"$PYTHON_BIN" research/throughput/accelerator.py --device cpu --model research/throughput/incumbent.bin --inputs research/throughput/inputs.json --reference research/throughput/results/native-reference.json
CARGO_BUILD_JOBS=2 CARGO_TARGET_DIR=local/throughput/prototype cargo build --release --locked -p splendor-arena --features research-batching --example flywheel_data
python3 research/throughput/queue_runs.py --python "$PYTHON_BIN" --output local/throughput/queues-repeat
```

If dependencies are installed with `--target`, set `PYTHONPATH` to that directory.
`queue_runs.py` uses `local/throughput/coreml-deps` and the prepared direct binary.
Use a new Core ML package path for a different checkpoint; the package cache is
named from the model stem and is intended for these frozen models only.
Queue settings and complete commands are saved in `queues.json`. Accelerator
probes remain opt-in and default batching size is zero.

## Preserved evidence

Run `python3 research/throughput/verify_results.py` to audit final record hashes,
paired data hashes, completed-game counts, derived throughput, frozen models,
and available local evidence. The final audit verified 181 local artifacts.


[summary.json](results/summary.json) contains computed speed ratios and exclusions.
[local-artifacts.json](results/local-artifacts.json) inventories source evidence,
logs, raw records, and local training shards by size and SHA-256. Complete
benchmark JSON (including process samples and ordered game records), profiler
captures, assembly, rejected prototype source, and failed-attempt logs are
compressed under `results/raw`. These archives can be inspected with Python
`gzip` or `gzip -dc`. The final raw training shards stay compressed under
`local/throughput/final-confirmation`; queue shards remain under
`local/throughput/queues`. They are deliberately outside Git but are preserved
on this host and identified by the manifest. The earlier pilot script removed
raw shards after hashing; the two unique datasets were regenerated and their
original byte hashes verified, then saved compressed under `paired`. Recovery
runs are not timing evidence.

The current scripts, fixtures, frozen models, and raw records supply a
reproducible path. Original plans preserve the exact measured script hashes.
Later lint-only research changes have a different source fingerprint from the
measured queue prototype (`a2e903323af938d0`). Production final results are
identified by the exact committed source `1505ac8794c53416`.
