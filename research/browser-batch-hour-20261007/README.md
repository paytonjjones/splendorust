# Registered one-hour test

Compare batch1, batch2, and batch8 directly with the same frozen weights and
five seconds per whole turn. Use a one-billion simulation ceiling so the time
limit should bind. The round robin rotates matchup order and plays both seats
on each fresh setup. Run one search at a time.

The wall budget began at 14:57:59 UTC on 2026-10-07. Play stops at 15:52:59 UTC.
The final five minutes are for analysis and native replay checks. Process the
registered 24-game reservoir in order until the cutoff. Do not use outcomes
to choose how long to run. Report reserved games that did not start separately.
Keep started but unfinished games as unknown, with replay checkpoints.

The old four-game test took 695.54 seconds of gameplay. It kept a 6,400-simulation
ceiling. This new test changes that ceiling, uses fresh setups, and adds batch2.
Do not pool the old outcomes into this result.

PLAN.json fixes the schedule, source, WASM, model hashes, and deadlines.
The source is web/src/batch-hour.worker.ts and web/scripts/test-batch-hour.mjs.
The controller finish.py saves SUMMARY.json, RESULTS.md, replays.jsonl,
replay-check.log, and FINISHED.json when the owned browser runner exits.
Read FINISHED.json to check that analysis and replay passed.

No production engine choice is changed by the test. A point lead alone does
not establish superiority. The result applies only to this backend and budget.
