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

Normal cycles use one fixed 2,000-game paired gate and 14 threads on this host.
E44 measured about 2.5x throughput versus four threads. Keep 20,000-game runs
outside the inner loop for milestones, external claims, or ambiguous results.
Do not repeatedly inspect fixed 95% intervals as an early stopping rule. Select
models from bounded playing strength, not loss. Do not grow the old low-budget
corpus without evidence that more data increases strength per total wall time.

## Next experiment

No E47–E51 job remains active. All reserved gates are complete. This thread
proposes independent policy/value feature encoders: train policy features while
keeping the incumbent value function exact. No E52 seed or settings are
registered yet. Register the hypothesis and full settings before changing the
agent. Measure native latency and fixed-compute strength.

The native arena needs no Python ML framework. All E47–E51 models and failed
results are preserved. E48 proves that more search produces stronger teachers;
it does not prove that training can transfer that strength. No later student
has confirmed a second learning gain. The driver supports policy-only training
and greedy-visit targets as well as the existing native architectures.

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
