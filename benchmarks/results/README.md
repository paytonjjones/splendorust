# Benchmark result records

`native-20260929.json` and `aligned-20260929.json` are the baseline run files.
Each file retains raw repetitions, commands, source and binary hashes, hardware,
versions, timing scope, outcomes and confidence labels. `index-20260929.json`
links the baseline files and record archives with SHA256 hashes.

Files with `smoke-` in their name are validation runs. Their short timings are
preliminary and do not enter the baseline ranking. Incomplete games remain in
all requested-trajectory counts. A completed game is never inferred from a cap,
block or unsupported branch.

Aligned compressed records contain one normalized final-state record per case.
The same record-set hash must match both engines, worker counts and repetitions.
The archive name includes the corpus hash so a different corpus cannot replace
an older archive. Regenerate the corpus from its recorded master seed and count
with `benchmarks/make_corpus.py`.

Search safety and the rejected Search32 self-play diagnostics are retained in
[`docs/results/two-player-policy`](../../docs/results/two-player-policy/README.md).
Those promotion and diagnostic runtimes do not enter the speed ranking.
