# Stronger AlphaZero search run: handoff

The 1,000-game run is active. It uses master `17792000000`, 500 paired setups, 64 shards, candidate PUCT6400/depth64, and pinned AlphaZero with 6,400 active MCTS simulations. The AlphaZero checkpoint still declares 800 simulations. This run is a separate search-budget diagnostic. It does not replace the confirmed AlphaZero800 result.

At launch verification, the owner, MPS service, and scheduler were alive. The verifier saw 64 shard headers and did not read game outcomes. See [the launch receipt](../artifacts/opponent-search-launch.json) for process IDs, receipt hashes, configuration, and deadlines.

The schedule cutoff is `2026-10-05T06:12:57.796480Z`. The campaign cutoff is `2026-10-05T06:27:57.796480Z`; the driver reserves 15 minutes for replay and reports. The original Sprint 48 deadline is later. Use the earlier driver cutoff.

There is a known completion issue. The pinned AlphaZero config is a dotdict. The MCTS reads its `numMCTSSims` attribute, which is set to 6,400. The serialized mapping in `external_config` retains the checkpoint value 800. The current scheduler completion validator expects that mapping to equal 6,400. It may reject valid shard output before merge.

Do not rerun this master or change its seeds. Keep every shard and frozen input. Do not patch shard headers to claim 6,400 in the checkpoint mapping. A separately reviewed recovery must validate the completed raw games and active MCTS evidence, and report both values: checkpoint mapping 800 and active MCTS budget 6,400. Do not inspect partial game outcomes while the schedule runs.

The original native proof remains `confirmed_decisive_native_win` against the unchanged AlphaZero800 checkpoint. The completed 256-game canonical screen scored 59.1796875% with a 95% interval of 42.029052–76.330323%; it retained the canonical baseline because it did not confirm a gain.

The separate `recover_completion.py` passed 25 follow-up tests. Its detached
`--wait --recover` process waits until the original driver, service, scheduler,
and shard workers stop. It writes only to
`local/research/sprint48/opponent-search-6400-recovered`. It requires every
original shard to finish, all 1,000 rows, the registered 500 paired seeds, and
source, artifact, candidate-profile, and opponent-identity bindings. It retains
the original checkpoint mapping of 800 and records active MCTS 6,400. Replay,
summary, and evidence commands use the original campaign cutoff. A timeout or
incomplete sample is a failed check; it must not produce a strength claim.
The tool does not promote a champion. The final result still needs independent
review, archive verification, and delivery. See the completion watcher launch
receipt under `research/sprint48/artifacts/` for its process ID and log.
