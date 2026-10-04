# Final campaign delivery

Use this checklist only after `final-native-retry/run.json` reports
`status: complete`. Do not change the frozen schedule or inspect partial
outcomes to change the run. The registered result rule is in `RESULTS.md`.

1. Check `run.json`, `arena-command/exit.json`, `replay.json`, `summary.json`,
   and `evidence.json`. Require status `complete`, `run.json.games_verified` =
   1000, `replay.json.checked_games` = 1000, `evidence.json.games` = 1000,
   `evidence.json.setup_blocks` = 500, and an empty
   `evidence_rejections` list. Require the raw SHA256 in `run.json`,
   `replay.json`, and `evidence.json` to equal the SHA256 of
   `arena/games.jsonl`. Match each script hash to the frozen source map:
   replay and evidence have `script_sha256`; summary has `source_sha256`.
   Require `summary.json.games` = 1000. Check status counts against the
   registered no-action rule (at most one percent); record all credit bounds,
   including caps-as-unknown sensitivity. Keep every raw row and every worker
   receipt. Do not repair the result by dropping a row.
2. Check `final-freeze.json` and `campaign-context.json` against the start
   archive. Require freeze ID
   `feed64ad3e0555699264972c1a086e305e0b7c17e311dfe3560f88e956d97e58`, master
   `17790000000`, 1000 games, PUCT6400, depth64, world3, chance3, dynamic FPU,
   64 workers, MPS FP32 batch32, and the selected first-onehot model SHA
   `ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
   Match the source, binary, checkpoint, descriptor, and export hashes in
   `run.json` to the freeze and context receipts.
3. Make a new local snapshot of the full final output. Keep all schedules,
   raw rows, replay and evidence, model descriptor/export/parity receipts,
   source copies, binary hashes, cost receipts, commands, logs, and process
   receipts. Do not archive a live output directory.
4. Deduplicate only byte-identical inputs. Replace `input/candidate.pt` with a
   hash-bound reference to `research/training_strategy/artifacts/core`, member
   `first/onehot/runtime.pt` (manifest SHA256
   `c413a533ce69648d5f69994abd0f8458c8f70f33ae2a12b72b351bdd1f7f9399`).
   Replace copied files under `binaries/` only when their hashes match members
   in `artifacts/development-07` (manifest SHA256
   `14fbb3ca9619cbfbbad90598da62f3041d89df6482e7f00f2ed7d79eb9be511a`). Keep
   the generated service descriptor and all descriptor receipts. Add a
   reference JSON with each omitted path, SHA256, archive manifest SHA256, and
   member path. Keep every other file unchanged.
5. Pack the snapshot with the existing helper. Use provenance mode because
   the final run is an evidence archive, not a training study:

   ```sh
   python3 research/training_strategy/archive_results.py pack \
     --provenance final:local/research/sprint48/final-archive-snapshot \
     --output research/sprint48/artifacts/final-native
   ```

   The helper uses 48 MiB chunks and records compressed and uncompressed
   hashes. Save the manifest SHA256 and file count.
6. Restore the archive to a new local path with the helper's `restore` command
   and the manifest SHA256. Check that every file restores and that every
   hash-bound reference resolves to the stated existing archive member. Keep
   the restore receipt with the delivery notes.

The final outcome rule is fixed before this run. The archive step must not
select a checkpoint, change a result, or start another game.
