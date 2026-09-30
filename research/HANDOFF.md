# Learning research handoff

The accepted research teacher is `research/e41/cycle-0/model/model.bin` and its
matching `model.pt`. Native SHA256:
`d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600`.
Its fresh 20,000-game test scored 54.71% against the bootstrap, with one blocked
game kept as unknown. Strict promotion rejected that incomplete run; research
selection used conservative missing-outcome bounds. E26 is the last strict
promotion. One learning gain is established; repeated improvement is not.
There is no established external best-in-class ranking.

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

Normal cycles use one fixed 2,000-game paired gate and 14 threads on this host.
E44 measured about 2.5x throughput versus four threads. Keep 20,000-game runs
outside the inner loop for milestones, external claims, or ambiguous results.
Do not repeatedly inspect fixed 95% intervals as an early stopping rule. Select
models from bounded playing strength, not loss. Do not grow the old low-budget
corpus without evidence that more data increases strength per total wall time.

## Active work

Architecture changes are stopped after evaluator feedback. E54 collects5,000
training and1,000 development games at800 simulations, using the accepted
bootstrap teacher. It captures alternate inputs for opponent-blind observations.
The actual native generation process is controlled by this thread; its run is
`local/research/e54/flywheel`. The next screen is1310000000. E55 is the paired
multi-view control on the same corpus, with screen1320000000. Do not duplicate
these seed streams. Full settings and corrected training seed800000007 are in
`EXPERIMENTS.md`. Data and Torch remain under this worktree's ignored `local/`.

`--selection-rule provisional` keeps a fixed `champion.json` and a separate
exploratory `best.json` lineage. After one fixed2,000-game screen, requested-
schedule worst-case point credit above50.5% can advance the lineage. This is
not statistical confirmation. Strict decisions and95% intervals remain saved.
Missing outcomes remain unknown. Do not apply this new rule to completed E53
or earlier gates. After at most three candidate generations, assess the frozen
endpoint against the fixed champion at reserved3310000000,20,000 paired games.
The champion changes only after independent supporting evidence.

The eight-view diagnostic is exact when there is no opponent blind reservation.
In the explicit blind stress cohort, mean legal-policy TV is6.3%,and11.8% of
argmax choices differ from the mean policy. Native self-play blind frequency
is measured during collection. Stress frequency is not ordinary-play frequency.
All completed models and negative results remain saved. The accepted teacher is
unchanged. The native arena needs no Python ML framework.

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
