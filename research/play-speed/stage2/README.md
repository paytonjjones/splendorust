# Reproduce the additional speed gain

This stage compares the final source state in BUILD.json with commit 7de6146,
the previous delivered candidate. The baseline executable hash matches the
candidate executable in ../confirmation.json. All comparisons use the same
locked, pinned release settings and existing seal256-intersection-v1 contract.

Build a separate checkout at 7de6146 with:

```sh
cargo build --release --locked -p splendor-arena --features benchmark-compat \
  --example aligned_worker --example benchmark_worker
```

Copy its executables into the final checkout as
`local/play-speed/stage2/baseline-aligned` and
`local/play-speed/stage2/baseline-native`. Build the final checkout with the same
command, then copy its executables as `final-aligned` and `final-native` in that
directory. Do not run builds or other benchmarks during measurement.

```sh
python3 benchmarks/make_corpus.py --count 1024 --seed 110000001 \
  --output local/play-speed/stage2/trace-corpus.json
python3 research/play-speed/stage2/trace_check.py
python3 benchmarks/make_corpus.py --count 240000 --seed 111000001 \
  --output local/play-speed/stage2/confirmation-corpus.json
python3 research/play-speed/measure.py \
  --baseline local/play-speed/stage2/baseline-aligned \
  --baseline-commit 7de6146 \
  --candidate local/play-speed/stage2/final-aligned \
  --corpus local/play-speed/stage2/confirmation-corpus.json \
  --output research/play-speed/stage2/confirmation.json
python3 research/play-speed/native.py \
  --baseline local/play-speed/stage2/baseline-native \
  --candidate local/play-speed/stage2/final-native \
  --output research/play-speed/stage2/native.json \
  --players 2 --target-seconds 1.8 --max-count 1200000
python3 research/play-speed/summarize.py --directory research/play-speed/stage2
```

The aligned measurement keeps full canonical legal generation, complete numeric
projection ordering, policy selection, checked transitions, per-game clocks and
record collection in the timer. Setup, final snapshots and JSON serialization
remain outside. Each policy uses seven alternating repetitions with the same
240,000 cases. All cases and incomplete statuses stay in the result.

Native measurements keep setup and final digest in timing. They cover both
random and native greedy at 1/4/8 workers with two players. Greedy differs from
aligned fixed. The pilot fixes the work count for each configuration before
seven repetitions. Outcomes are compared for every repetition.

PLAN.md records hypotheses and failed branches. The 80,000-case screens have
one repetition each; their times are below one second and are preliminary.
The final confirmation uses fresh seeds after the candidate freeze. TRACES.json
and its archives retain the broader exact trace checks. BUILD.json records the
source and executable hashes. VALIDATION.json and logs record local checks.

The first-stage report, BUILD.json and MANIFEST.json in the parent directory are
historical artifacts for source commit 7de6146. Later script and source changes
do not update those historical receipts. Use that commit to reproduce stage one.
