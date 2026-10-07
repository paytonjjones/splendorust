# Direct browser batch-search check

Batch-eight won **1 game** and lost **3 games** against sequential search.
All four games finished. None was blocked or capped. This small sample does
not establish a strength gain, strength parity, or a small regression margin.
The conservative interval over the two setup pairs covers 0–100% win credit.
Do not use this result to promote a research champion.

The user requested deployment before this test. Batch-eight remains deployed
at [the public site](https://splendorust.pages.dev). The deployed code is
`762289d`; the immutable deployment is
[60833644](https://60833644.splendorust.pages.dev).
The confirmed native research champion record is unchanged.

## Fixed test

Both engines used Chrome 154 WebGPU FP32, the same frozen Entity weights,
canonical rules, PUCT depth64/world3, a 6,400-simulation ceiling, and a
five-second whole-turn limit. Search stopped 100ms early for internal choices.
Sequential search used the batch-one graph; the candidate used batch-eight
with virtual visits and delayed leaf backups. One game and one search ran at
a time. Both engines received their own public observation. Two fresh setups
were played in both seat orders. [PLAN.json](PLAN.json) fixed these settings
before outcomes. The first browser startup attempt failed before any game;
its metadata is retained in startup-failed.jsonl.

| Setup | Batch-eight seat | Batch-eight result | Score, batch-eight–sequential |
| --- | ---: | --- | --- |
| 1 | 1 | Win | 15–13 |
| 1 | 2 | Loss | 10–16 |
| 2 | 1 | Loss | 13–17 |
| 2 | 2 | Loss | 13–18 |

## Measured cost

| Search | Mean simulations per searched turn | Median searched-turn time | Simulations/s | Inference positions/s |
| --- | ---: | ---: | ---: | ---: |
| Sequential | 3,043 | 4.901s | 695 | 490 |
| Batch-eight | 6,400 | 2.216s | 3,102 | 2,674 |

Batch-eight had 4.46× simulation throughput and 5.46× inference throughput
in this workload. It stopped at the simulation ceiling before its time limit.
Its extra time did not produce further simulations. The largest full-turn
times were 4.907s for sequential and 2.451s for batch-eight.
Timing includes the browser search, checked transition, and paired-state
verification. Throughput sums work over elapsed time for turns with search;
it excludes turns with zero simulations. These measurements apply to this
host, these games, and these search settings.

## Checks and reproduction

Both engine instances had the same full state and action journal after every
checked legal decision. Native replay validation checked all four saved games.
Format, strict release workspace Clippy, locked release workspace tests with
all features, TypeScript, and 39 log-backend checks passed. Six live asset
hashes matched the deployed build. See RUNTIME.json, public-assets.json,
replay-check.log, and the saved check logs.

Keep [games.jsonl](games.jsonl), [replays.jsonl](replays.jsonl),
[SUMMARY.json](SUMMARY.json), and [backend.json](backend.json).
The page used hardware WebGPU with no special browser flags.
The browser harness is web/src/batch-strength.worker.ts and
web/scripts/test-batch-strength.mjs. It uses the deployed WASM search and
checked model graphs. Start the Vite development server on port4175, then
run the harness from web. Use new seeds and output paths for a new test;
these seeds are consumed evidence. Analyze the retained run with analyze.py.
