# AhinLendor comparison

The user approved this follow-up in [MANDATE.md](MANDATE.md). The deadline
remains **2026-10-05 19:35:52 UTC**. See [PLAN.json](PLAN.json).

The fixed AlphaZero6400 test must finish first. Keep its model, 1,000 games,
master seed 17792000000, and completion checks fixed. Its separate completion
checker must preserve the original shards. See
[the handoff](../sprint48/opponent_search/HANDOFF.md).

AhinLendor is pinned to `96e6f2daff83147495826c4a2073dc3c9c856cc9`.
The public source has no trained checkpoint or documented download. The user
does not have the checkpoint. The flagship strength test is blocked. Do not
contact other people or label substitute weights as the flagship.
See [the source audit](SOURCE_AUDIT.md).

The work that can proceed is the canonical rules audit, public-observation
adapter, CPU interface checks, and matched raw-engine measurements. These
checks cannot establish playing strength. The adapter must report unsupported
choices and keep them in any future game evidence. It must not supply a hidden
opponent card, setup seed, or true future deck order to an agent.

Read [the rules audit](RULES_AUDIT.md) and
[the adapter instructions](adapter/README.md) before a match. Any later timed
match must give each agent one cumulative 20-second budget per complete turn,
including payment, token returns, and noble choices. Freeze the checkpoint,
search settings, fresh paired seeds, and sample count before its outcomes.

The CPU scripted smoke completed 112 decisions at seed 1002. It exercised
main, payment, return, and noble phases, with hidden opponent reservations
redacted. The 21 adapter tests passed. See
[the smoke receipt](adapter/artifacts/smoke-full-phases.json). This used no
trained weights or search. Its post-call clock guard cannot enforce a hard
20-second search deadline; a strength runner still needs that control.

The [raw-engine report](engine/RESULTS.md) records four matched sampled worlds
and three repeats per operation. Full initial-state and post-take checks pass.
The run shared this Mac with the AlphaZero job. Its results support only the
listed operation scopes. A separate full-turn trajectory workload is in
progress; it has no accepted result yet.

Use the pinned local inference Python for extension checks. The extension is
an ignored local build. Keep its source pin, build receipt, fixture hashes,
timing scope, and shared-host load with the evidence. Run Rust checks locally;
GitHub Actions remains disabled.
