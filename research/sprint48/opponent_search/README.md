# Strong AlphaZero search diagnostic

This profile keeps the pinned AlphaZero source, checkpoint, rules, and native
referee. It changes only the `numMCTSSims` value passed to the pinned MCTS.
The profile name is `alphazero-native-search-budget-diagnostic-v1`; it is a
search-compute diagnostic, not the unchanged AlphaZero 800 benchmark.

The original final campaign driver, freeze, and confirmed 800-simulation
result remain unchanged. This isolated follow-up uses `run_campaign.py`; it
checks the frozen source and checkpoint, reserves the one-use master, starts
the MPS service and schedule, then validates replay and evidence. The no-flag
command is read-only preflight. It does not reserve seeds, create the campaign
output, or start a service. The `--execute` command performs those actions.

The registered plan is fixed: master `17792000000`, 1,000 games in 500 paired
blocks, pinned AlphaZero at 6,400 simulations, and Entity PUCT at 6,400
iterations / depth 64 / world pool 3 / chance universes 3 / dynamic FPU. The
candidate uses the frozen one-hot checkpoint, MPS FP32 batch 32, 64 workers,
and the registered service configuration. The run has a 14-hour job budget and
must stop by the original deadline, `2026-10-05T19:35:52Z`. The launcher rejects
an incorrect or already-used reservation. Do not invoke `schedule.py` directly
for this campaign.

Run the CPU-only preflight first, then execute only when the campaign owner
authorizes launch:

```text
/Users/payton.jones/.codex/worktrees/9424/splendorust/local/strength/inference/bin/python research/sprint48/opponent_search/run_campaign.py \
  --output local/research/sprint48/opponent-search-6400

/Users/payton.jones/.codex/worktrees/9424/splendorust/local/strength/inference/bin/python research/sprint48/opponent_search/run_campaign.py \
  --output local/research/sprint48/opponent-search-6400 --execute
```

The raw header records the pinned checkpoint setting (800) and the diagnostic
setting, with hashes for wrappers and unchanged native sources. Ordinary
native replay checks actions, chance draws, observations, states, and rewards;
it does not rerun policy search, so it accepts the diagnostic MCTS count.
