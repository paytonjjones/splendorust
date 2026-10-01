# Learning research handoff

The confirmed research champion is `research/e56/model/model.bin`, with matching
`model.pt`. Native SHA256:
`055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41`.
`research/CHAMPION.json` is the public pointer. Its independent 20,000-game
check scored55.26% against the prior cycle0 champion at the same128-simulation
budget, CI54.13–56.39%,all games complete. The strict gate promotes.
The learning loop has now produced a second confirmed gain. E56's51.15%
small step over E54 remains unconfirmed by itself. External rank is unestablished.

| Experiment | Result | Decision |
|---|---|---|
| E42, 256-simulation teacher | 51.89%, 5,000 complete games | Retain incumbent |
| E42, 800-simulation teacher | Selected identical epoch-zero weights | No trained challenger selected |
| E43, aligned teacher targets | 52.80%, 5,000 complete games | Retain incumbent |
| E45, faster gated student | 6.40%, 1,999/2,000 complete | Reject; missing outcome unknown |
| E46, bit inputs and distillation | 33.375%, 2,000 complete | Reject |
| E47, deeper teacher | 51.225%, 2,000 complete | Reject; slower inference |
| E48, same model at 256 / 800 simulations | 60.20% / 70.625%, 2,000 complete each | Stronger teachers at higher compute |
| E49, policy head with frozen critic | 51.68%, fresh 5,000 complete | Reject after ambiguous screen |
| E50, matched full-network control | 50.65%, 2,000 complete | Reject |
| E51, greedy late policy targets | 49.95%, 2,000 complete | Reject |
| E52, independent policy features | 51.10%, 2,000 complete | Reject; critic exact |
| E53, budget800-only small corpus | 51.55%, 2,000 complete | Reject under its registered rule |
| E54, full-volume budget800 corpus | 56.775%, 2,000 complete; CI52.51–61.04% | Strict screen passes |
| E55, paired multi-view control | 49.525% versus E54, 2,000 complete | Reject |
| E56, next generation | 51.15% versus E54, 2,000 complete | Provisional advance;20k milestone55.26% passes |

Normal cycles use one fixed 2,000-game paired gate and 14 threads on this host.
E44 measured about 2.5x throughput versus four threads. Keep 20,000-game runs
outside the inner loop for milestones, external claims, or ambiguous results.
Do not repeatedly inspect fixed 95% intervals as an early stopping rule. Select
models from bounded playing strength, not loss. Do not grow the old low-budget
corpus without evidence that more data increases strength per total wall time.

## Active work

Architecture changes were paused to diagnose distillation. Small experiments
are a default, not a design limit. Reassess the paradigm after each campaign.
If evidence shows a structural limit, test a larger model, search, or training
change. Best-in-class strength is the goal; code size is not the goal. E54's5,000-game800-simulation corpus
produced281,432 training positions and a56.775% strict2k screen gain. E55's
paired random-view training control did not improve strength. E56's frozen
endpoint passed its independent20k milestone. E57 native controls scored
95.64% against Search128 and97.625% against Strong; the16-simulation student
scored82.88% against Search128 at lower measured decision cost. Four/five
incomplete control games remain unknown. The external400-game AlphaZero
rerun is complete:209 complete,191 unsupported;59.81% conditional credit
cannot establish a rank. All400 histories passed canonical replay checks.

E58 completed its 5,000-game teacher corpus and advanced provisionally at
51.8% over E56 in 2,000 complete games. E56 stays the confirmed champion.
E59 completed a 50-epoch control and advanced provisionally at51.3% over
E58 in2,000 complete games. It selected epoch7; fit KL barely changed.
Keep10epochs as the normal budget. `research/LINEAGE.json` points to E59.
The3540m screen is complete; do not reuse it. E60 found 24.1% mean pairwise
teacher policy TV on 62 fixed observations. E61 completed its paired two-teacher control at48.825% versus E58 and was
rejected. The3580m E59 endpoint milestone scored51.705% over E56 in
20,000 complete games,CI50.58–52.83%. It supports a small gain at zero
margin but does not pass the strict1% margin. Keep E56 champion,E59 lineage.
E62/E63 now test a modern residual correction branch over the fixed E59
base. Initial function identity and fixed-base integrity are required; record
real inference cost and both fixed-node and measured-cost screens.
Data and Torch remain under this worktree's ignored `local/`; do not duplicate
active seed streams. Use the confirmed E56 model for further teacher work.

`--selection-rule provisional` keeps a fixed `champion.json` and a separate
exploratory `best.json` lineage. After one fixed2,000-game screen, requested-
schedule worst-case point credit above50.5% can advance the lineage. This is
not statistical confirmation. Strict decisions and95% intervals remain saved.
Missing outcomes remain unknown. Do not apply this new rule to completed E53
or earlier gates. After at most three candidate generations, assess the frozen
endpoint against the fixed champion in20,000 paired games. The prior3310m
assessment is complete; the current campaign reserves3580m.
The champion changes only after independent supporting evidence.

The eight-view diagnostic is exact when there is no opponent blind reservation.
In the explicit blind stress cohort, mean legal-policy TV is6.3%,and11.8% of
argmax choices differ from the mean policy. Native self-play blind frequency
is measured during collection. Stress frequency is not ordinary-play frequency.
All completed models and negative results remain saved. The confirmed
champion is `research/e56/model/model.bin`, SHA055c42...f41. Each new campaign
keeps its starting champion fixed until an independent milestone passes. E54 and E56 checkpoints are both public and can be evaluated
from main. The current endpoint was frozen before all final-assessment outcomes. The native arena needs no Python ML framework.

## Local data and parallel work

Large data and the pinned Torch environment are ignored, and remain under
`/Users/payton.jones/.codex/worktrees/2311/splendorust/local/`.
E40 data: `research/flywheel-e40/cycle-000/{train,dev}`.
E42 data: `research/flywheel-e42-{256,800}/cycle-000/{train,dev}`.
E43 development data: `research/e43/dev800.bin`.
The interpreter is `strength/inference/bin/python`; bootstrap training also
uses the frozen upstream source/checkpoint at `strength/external/alphazero`.
A separate worktree must reuse these local assets explicitly. Do not remove
this worktree or overwrite its datasets while research continues.

Use separate branches for parallel work. Preserve completed experiments,
checkpoints and reserved seed streams. Native inference/data throughput can be
worked on independently of the next model experiment. Read `research/README.md` for
commands and `research/REPORT.md` for evidence limits. Rust changes require
format, strict workspace Clippy, and release locked workspace tests.
