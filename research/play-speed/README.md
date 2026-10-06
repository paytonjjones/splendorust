# Reproduce random and fixed play speed

The baseline is e429c72. The final candidate is the source state whose file
hashes are in BUILD.json. Use the pinned Rust toolchain and locked dependencies.
The existing aligned adapter contract remains seal256-intersection-v1.

Build the baseline checkout with:

```sh
cargo build --release --locked -p splendor-arena --features benchmark-compat \
  --example aligned_worker --example benchmark_worker
```

Copy its two executables into this checkout as
`local/play-speed/baseline-aligned` and `local/play-speed/baseline-native`.
Build this checkout with the same command and copy its executables as
`local/play-speed/final-aligned` and `local/play-speed/final-native`.
Do not run builds or other benchmarks during timing.

```sh
python3 benchmarks/make_corpus.py --count 160000 --seed 107000001 \
  --output local/play-speed/confirmation-corpus.json
python3 research/play-speed/measure.py \
  --candidate local/play-speed/final-aligned \
  --corpus local/play-speed/confirmation-corpus.json \
  --output research/play-speed/reproduction.json
python3 research/play-speed/native.py
python3 research/play-speed/summarize.py
```

`measure.py` uses the current worker interface. It checks the baseline and
candidate legal-key lists, selected keys, state traces and outcomes over 64
cases per policy before timing. It then compares all normalized final records,
operation counts and incomplete statuses in every repetition. Individual
latency values are excluded from equality. Seven repetitions alternate order.
Each repetition uses 160,000 identical cases. Setup and JSON serialization
remain outside the gameplay timer. Projection, checked transitions, per-game
clocks and record collection remain inside it.

`native.py` keeps persistent workers and measures full canonical random and
native greedy choices. It checks final digests, decisions, turns and all status
counts over matched seed ranges. One worker covers 2/3/4 players; 4/8 workers
cover two-player scaling. Native greedy is a different policy from aligned fixed.
Its count is calibrated from a pilot and fixed across seven repetitions.

The core-only and buffer screens use 80,000 cases at seed 106000001 and one
repetition. They are preliminary. Their source states reuse core changes from
0de6afe; the buffer screen then replaces the aligned projection Vec with
ArrayVec. These source changes are recorded in PLAN.md and the final diff.
Raw screen results remain in core-screen.json and buffer-screen.json.

`BUILD.json` records source file hashes and release settings. Results store
binary, corpus and record hashes. Record archives include all attempted cases.
`profile-fixed.txt` is the baseline CPU sample, taken outside final timings.
`VALIDATION.json` and the corresponding logs record local checks.
