# Canonical engine throughput

Read RESULTS.md for the measured scope and limitations. PLAN.md records the
hypotheses and finite budget before each change. SUITE.json fixes the four
coverage-selected traces. FROZEN.json and SECOND_FROZEN.json identify both
confirmation candidates; FIRST_FINAL_SUMMARY.json retains the failed first
confirmation. SUMMARY.json is the second confirmation; REVERSED_SUMMARY.json confirms the
same production binary with each engine order reversed. AUDIT.md describes
the original timed paths and real callers.

Use the repository's pinned Rust toolchain and Cargo.lock. Put the unchanged
AhinLendor checkout at local/strength/external/ahinlendor, at commit
96e6f2daff83147495826c4a2073dc3c9c856cc9. The runner checks that commit and hashes
its engine sources. The core remains independent of this external checkout.

Build the strict original baseline from commit 534cd40. The preparation script
checks the recovered original source and the original trajectory-source hash.
It only adds repeat/count arguments and permits complete traces with partial
category coverage. It leaves the original timed loop unchanged.

```sh
python3 research/engine-throughput/prepare_baseline.py
CARGO_TARGET_DIR=local/research/engine-throughput/baseline-target cargo build --release --locked --manifest-path local/research/engine-throughput/baseline-source/Cargo.toml -p splendor-arena --features benchmark-compat --example engine_baseline --bin splendor
python3 research/engine-throughput/run.py local/research/engine-throughput/reproduction --with-original-baseline --seeds 424262 424268 424285 424287 --games 100000 --repeats 7
python3 research/engine-throughput/summarize.py local/research/engine-throughput/reproduction --output local/research/engine-throughput/reproduction-summary.json
python3 research/engine-throughput/run.py local/research/engine-throughput/reproduction-reverse --skip-build --with-original-baseline --seeds 424287 424285 424268 424262 --games 100000 --repeats 7
CARGO_TARGET_DIR=local/research/engine-throughput/target cargo build --release --locked -p splendor-arena --features benchmark-compat --bin splendor
python3 research/engine-throughput/runtime.py --output local/research/engine-throughput/runtime-reproduction
```

Each output directory must be new and empty. Schedule CPU jobs in sequence.
The runner records command results, compiler versions, load, process names,
source and binary hashes, exact trace hashes, operation counts, and outcome
checks. It retains failures. C++ uses C++17 -O3 -DNDEBUG -flto. Rust uses the
workspace release profile, thin LTO, one codegen unit, and the locked toolchain.

The restored engine_trajectory example and original C++ replay remain available
as the original benchmark contract. The restored Rust example explicitly uses
the reference enumeration; its current Action storage is eight bytes. For an
exact comparison with the original seven-byte storage, use engine_baseline.
New full profiles are named separately in engine_profile and ahin_profile.
The C++ predecoded profile still generates the full legality mask and calls
checked applyMove. Rust full_validated_decision still generates every canonical
legal action and applies every payment, return, and noble decision.

The supplied-action and cached-component profiles are diagnostics. They cannot
establish complete-turn throughput. Snapshot checks, ordered-list comparisons,
observations, and outcomes run outside timed loops. The complete lists/masks,
selected inputs, and resulting states have compiler barriers inside timing.

The evidence archive preserves receipts, raw CSV/log files, all scanned traces,
failed build/check logs, insufficient screens, old source snapshots, final
checks, and before/after runtime records. It excludes build directories and
binaries; binary hashes and build commands identify them. Private benchmark
decks in these fixtures must never become agent inputs.
