# E78: large root correction on fixed Gumbel teacher data

The candidate scores **49.925%** against E68 Gumbel128 in **2,000 complete games**, at128 simulations/depth16. The paired95% interval is45.594–54.256%. Reject the candidate; retain E68 and the provisional Gumbel search mode. E56 remains the confirmed champion.

A frozen E68 base plus a384-wide/six-block RMSNorm/SwiGLU correction has3,035,161 parameters. The correction runs once at the root, while the base supplies all leaves. Training uses the identical333,620-row E74/replay corpus,55,476 held-out rows,20 epochs, seed800000015, AdamW1e-4, batch1024 and MPS. Epoch2 is selected. Training takes270.64s; full run465.33s and arena89.48s under concurrent external-evaluation load. Native parity and frozen-base checks pass.

Held-out policy CE changes from1.99523 to1.96837; outcome Brier from0.216040 to0.216127. Later epochs deteriorate sharply; epoch20 CE is2.93326. The selected model's policy KL is1.42507 on fresh training rows and1.51822 on development. This result does not support another capacity increase on this corpus. It does not isolate label noise from optimization or representation limits.

Candidate native SHA256:`ee0a168090e80aa80f813ebdff3b5da22a5108af005e583d4f9fb24fefd983ab`.
Checkpoint SHA256:`6c48c8871566eb8339b34fb1d441e13e75f91fc9e8a50e55e95d2d91bf813ce8`.

All models, source snapshots, plans, raw arena records, intervals and negative decisions are preserved. E80 tests teacher target/execution alignment before further model changes. E79 separately tests the frozen strong teacher against the pinned native AlphaZero target.
