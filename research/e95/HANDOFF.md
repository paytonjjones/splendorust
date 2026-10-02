# E95 handoff

Stopped after the complete teacher corpus and replay audit. All6,000 games and336,636 transitions completed and replayed; training has280,710 rows and development55,926. Canonical replay/development dependencies add55,792/55,646 rows. The recipe therefore uses336,502 train and111,572 dev rows. Training and strength screens have not started. The waiting finish.py launcher was stopped at the user's request. CHAMPION remains E81; provisional LINEAGE remains E88. The best-in-class goal is not achieved.

## Current evidence

E92: E81 Gumbel128 scores27.325% against unchanged native AlphaZero800 in2,000 complete games; all111,034 transitions replay. Its conservative95% interval is23.0303–31.6197%. This is weak external strength. The native profile retains AlphaZero's private-information advantage; no canonical or equal-compute rank follows.

E89 failed to compound the public-root lineage. E93 fixed-budget consensus lost45.025%; do not collect consensus data or resume small search sweeps. E94 validated the stronger external-teacher data boundary. E95 now makes the structural supervision/representation change: direct pinned AlphaZero800 expert labels, comparable corpus volume, and deterministic public inputs at every search node.

The runtime uses143,470 parameters and75 input rows:392 public mean features,120 membership marginals,7 reservation fields,1 public rules flag and5 pads. Added projection columns start at zero; all parameters train. Native inputs retain native noble order, and canonical inputs retain canonical order. Old models keep their frozen sorted-noble contract. No private teacher state enters runtime inputs. All125 release tests, strict Clippy,8 native interface tests, old corpus byte checks and old native policy checks pass. Excluded gradient/export smoke checks pass; they are not strength evidence.

## Resume

The source workspace on this Mac is `/Users/payton.jones/.codex/worktrees/2311/splendorust`. It retains the pinned Python3.11/Torch2.5.1 environment, frozen worker binaries and raw datasets. Verified gzip archives of native data/context/history and canonical replay/development dependencies are committed under data/. restore_data.py restores exact row bytes without another teacher collection. Preserve this workspace until the next run has restored all dependencies.

From this workspace:

```sh
local/strength/inference/bin/python research/e95/restore_data.py
local/strength/inference/bin/python research/e95/finish.py
```

finish.py preserves existing archives, freezes its model plan, trains the registered10-epoch recipe, checks export and cost, and runs fresh canonical/native2,000-game screens at4870000000/4860000000. Cost failures retain diagnostic evidence but defer selection. It does not update champion pointers. Do not reuse E92 or the excluded pilots for training or checkpoint selection. Inspect the decisions before advancing a lineage. Keep GitHub Actions disabled and run required checks locally.

A new checkout also needs the pinned external Python dependencies and rebuilt native examples. Build with the pinned toolchain/Cargo.lock and `CARGO_TARGET_DIR=local/research/flywheel-target CARGO_BUILD_JOBS=2`; retain Cargo JSON output at local/research/e95/cargo-build.jsonl, then run build_cost.py to compile the cost control with those selected libraries. The existing workspace already has these binaries. Final native worker hashes are frozen after promotion checks so preflight builds cannot invalidate the recorded arena identity.

## Judgment

The immediate question is whether a genuinely stronger teacher can transfer strength into public inference at128 simulations. E95 answers that combined supervision/representation question; it does not isolate each change. A good dev loss is insufficient: require complete fresh playing evidence.

If training fits but playing strength still stalls, test teacher labels on student-generated states and history-conditioned beliefs. If the network fails to fit public teacher targets, test larger full-network capacity. Choose the next structural change from those results. Preserve a rigorous champion while allowing justified provisional gains. Reserve20,000-game confirmation for a milestone or an external dominance claim, outside the inner loop.

Collection cost was49.35min, paid once. Reuse this corpus for the next model trials. For future teacher collection, use more development shards and schedule both splits in one pool: the current development stage had onlyfive active jobs despite a14-worker limit. This is a scheduling issue, not a reason to reduce the strong-teacher corpus again.
