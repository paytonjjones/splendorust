# E88: public-root attention

Select E88 for the provisional research lineage. It scored 51.05% in 2,000 completed paired Gumbel128 games against E81. The conservative 95% interval is 46.8242–55.2758%. The strict gate retains E81. The preregistered provisional point rule selects E88; this is exploration, not a confirmed gain. The champion remains E81.

The attention branch has 101,139 trainable parameters. It uses 56 public board-row tokens and one public membership/context token, with width 64, four heads, and two blocks. The 142,406-parameter E81 base stays fixed and handles sampled-input search leaves. Only root inference uses attention and public means. Runtime inference is native Rust.

Training used 334,040 positions from the E87 strong-policy corpus and fixed replay, plus 55,646 development positions. Twenty epochs took 504.04 seconds. Development selection chose epoch 5. The selected model improves development policy loss from 1.592120 to 1.587053 and outcome Brier error from 0.207332 to 0.207295. The manifest architecture description uses a generic residual label; the checkpoint, SPATTN01 export, and saved model source identify the attention architecture.

Trained native export parity passed on 64 real inputs: maximum logit error 0.00001526 and policy/value error 0.00000259. The trained root-cost median is 1.128695 times E81, within the 1.15 cap. All 118 release tests and strict Clippy passed. Public-input invariance and fixed leaf/base checks remain covered.

The first native kernel exceeded the cost cap. Weighted-value accumulation across 16 lanes reduced the initial median cost to 1.112239 without approximate math or a change in summation order. Failed timings and source are preserved. Shared-host timings are not isolated performance claims.

This is the first provisional advance after E84–E87. The next cycle will generate fresh full-game teacher data from E88 at 800 simulations and continue this attention model. It will use new development and arena seeds. This tests whether the research lineage can compound small gains. It does not justify an external ranking.
