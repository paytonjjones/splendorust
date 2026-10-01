# E67: independent teacher queries on student trajectories

An optional actor budget controls moves and opening policy sampling. Independent
teacher agents supply policy/value targets on those actor observations. Agents
receive observations only. Existing collection remains the default.

Checks on 16 full games establish exact old/default raw-data parity, same-budget
actor trajectory parity, and unchanged 128-simulation actor states when teacher
budget changes from 800 to 256. Teacher labels change. Serial and parallel
collection are byte-identical. Inputs, masks, policies, outcomes, and separate
role work counts pass checks. Samples have 934 teacher-trajectory rows and 910
student-trajectory rows. These are validity checks, not playing-strength claims.

All 102 release workspace tests and strict Clippy pass. Source snapshots,
checks, manifests, commands in the logs, and data hashes are saved. Small binary
fixtures remain under ignored local/research/e67. No core rules, engine RNG,
replay semantics, or normal search defaults change. E68 tests whether this
state-coverage change can improve the fast student on a comparable-volume corpus.
