# Frozen E56 benchmark in the current workflow

The results commit `db43fe3` is integrated. The complete frozen evidence is under [e56-frozen/REPORT.md](e56-frozen/REPORT.md). All 158 original artifact hashes remain unchanged in that snapshot, including 46 lossless raw archives. Current `run.py`, `schedule.py`, `test_native.py` and `README.md` retain the later Gumbel/root-only work. The snapshot is an archive; execute its original reproduction scripts in a checkout of `db43fe3` so their repository paths and frozen source remain correct.

```sh
python3 benchmarks/strength/native/verify_e56.py
git worktree add --detach /tmp/splendorust-e56-reference db43fe3
```

Use the original report/README in that reference checkout for reproduction. Restore pinned local dependencies and frozen binaries as documented there. Use new output directories. The verifier checks hashes and exact decompressed bytes; it does not rerun policies or claim a new replay audit.

The 24,000 scheduled games completed and passed replay. Frozen E56 PUCT scored 23.395% in 20,000 games at 128 simulations, and 37.775% in 2,000 fresh games at 800 simulations. AlphaZero remained unchanged at 800 simulations. This is the `alphazero-native-32a27ac-v1` profile with its native rules and declared information advantage. It is not canonical, equal-information or equal-compute evidence. The larger-search result is not a training gain.

Workflow: keep approximately 2,000 paired games in the model-selection loop. Run this unchanged AlphaZero profile on selected milestone models with fresh seeds, recorded model/search hashes and complete replay. Keep 20,000 confirmations outside the hot loop. Do not pool the old E56 results with current E81 or a new search profile. Keep canonical champion claims conditional on their canonical opponents and budgets. Current E79 Gumbel800 evidence remains a separate endpoint, not a replacement for this archived E56 baseline.
