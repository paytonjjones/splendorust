# External playing-strength benchmark

Use the fixed target list and the approved profiles in [PROFILES.md](PROFILES.md).
The default engine and current policies stay unchanged. External source and
model dependencies stay under ignored `local/strength/`. Python 3.11 is needed:
upstream's pinned ONNX Runtime 1.16.3 has no Python 3.12 wheel. All dependencies
are pinned in `requirements.txt`.

```sh
python3 benchmarks/strength/setup.py
python3 benchmarks/strength/run_suite.py --output-dir results/strength-reproduction
python3 -m unittest discover -s benchmarks/strength -p 'test_*.py'
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --release --locked -- -D warnings
cargo test --workspace --all-features --release --locked
cargo build --release --locked -p splendor-arena --example strength_replay
python3 benchmarks/strength/verify.py
python3 benchmarks/strength/verify_native.py
```

`verify.py` checks the retained checked-in results. It replays every canonical
history through checked transitions and invariants. The setup manifest records
exact revisions, compiler, runtime, executable hashes and checkpoint hashes.
Each match header records binary and adapter hashes, configured budgets, rules,
observation profile, host and a reproduction command. Raw records include setup
blocks, rotations, chosen canonical/native actions, scores, status, reason,
normal terminal rewards and policy/total wall times. The suite uses fresh
confirmation seeds after screens. No settings are tuned from screen results.

Fixed simulations are different cost models. They do not establish equal
compute. Timings include IPC, sampled-state construction, conversion and first
inference/JIT work; concurrent runs share the host. No controlled fixed-wall-clock
strength comparison is claimed. Changing native MCTS termination to enforce a
clock budget would need a separate experiment. The native control is run separately
under native rules. Unsupported games are never converted into wins.

The original native screening summaries and raw JSONL are preserved. The
`*-audited.json` summaries correct zero-reward terminal classifications.
The rejected-temperature screen preserves an early adapter error: it applied
the upstream early-turn temperature for six rounds instead of six total turns.
It is excluded from rankings and confirmation. The first low-budget smoke used
the same error and is diagnostic only.

Earlier runs under `results/rejected-seed-coupling/` are excluded because
policy seeds were a reversible function of setup seeds. The exact earlier
runner is retained as `run-before-seed-fix.py.txt`. Final schedules use independent
master streams (policy 2,500,001 and sampling 3,500,001), with full identity
rotation. The final schedule is frozen in `run_suite.py`.
