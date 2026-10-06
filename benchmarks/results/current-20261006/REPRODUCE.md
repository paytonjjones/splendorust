# Repeat the comparison

Run from the repository root on macOS. Use a new output directory. Do not run
other builds or benchmarks during timing. These commands use the pinned Rust
toolchain and upstream C++ revisions. They do not change production rules.

## Build the aligned workers

```sh
cargo build --release --locked -p splendor-arena --features benchmark-compat --example aligned_worker
python3 benchmarks/external/setup_native.py seal256
mkdir -p local/strength/external
git clone https://github.com/inhabae/AhinLendor.git local/strength/external/ahinlendor
git -C local/strength/external/ahinlendor checkout --detach 96e6f2daff83147495826c4a2073dc3c9c856cc9
clang++ -O3 -DNDEBUG -std=c++17 -flto \
  -I local/strength/external/ahinlendor \
  -I local/benchmarks/external/seal256/src \
  benchmarks/adapters/ahin_aligned.cpp \
  local/strength/external/ahinlendor/game_logic.cpp \
  -o local/benchmarks/external/ahin-aligned
```

If AhinLendor is already present, check its revision and clean source instead
of cloning it again. The seal256 setup exposes its unchanged validation
method through a public interface. It rejects other source edits.

## Validate and measure

Run these commands in order:

```sh
python3 benchmarks/refresh_aligned.py --output local/benchmarks/new-comparison
python3 research/engine-throughput/run.py local/benchmarks/new-comparison/replay-forward \
  --seeds 424262 424268 424285 424287 --games 100000 --repeats 7
python3 research/engine-throughput/run.py local/benchmarks/new-comparison/replay-reverse \
  --seeds 424287 424285 424268 424262 --games 100000 --repeats 7 --skip-build
python3 benchmarks/summarize_refresh.py local/benchmarks/new-comparison
```

The aligned runner checks all card and noble tuples, then checks 1,024 full
traces per policy. Excluded pilots select one fixed count per policy before
measurement. A new run can select a different count. The archived run used
286,102 random cases and 225,717 fixed cases, with master seed 112000001.
`make_corpus.create(count, master, exported_seal_data)` recreates those cases.
Add the AhinLendor card and noble mappings from `aligned.json` to the corpus
under `ahin_core_to_native_cards` and `ahin_core_to_native_nobles`. Encode JSON
with sorted keys and separators `(',', ':')` to check the recorded corpus hash.

The runners reject changed sources, changed binaries, failed commands, and
mismatched records. The summary also checks the fixed replay trace hashes,
outcomes, operation counts, and both run orders. Keep failure receipts.

## Evidence files

- `build.json` and build logs: aligned build commands and results.
- `aligned.json`: source and binary hashes, host, corpus hashes, every timing,
  stop counts, validation, and medians.
- `*-records.json.gz`: normalized aligned records and trace checks. The JSON
  receipts contain their archive and record-set hashes.
- `replay-forward/` and `replay-reverse/`: build logs, traces, checks, raw CSV
  timings, command receipts, and source and binary hashes.
- `summary.json`: checked medians and 95% bootstrap intervals. The bootstrap
  uses 10,000 resamples and seed 20260928. It samples timing repetitions.
