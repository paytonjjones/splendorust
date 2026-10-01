# E81: verified-action distillation advances the research lineage

The candidate scores **52.0%** against E68 Gumbel128 in **2,000 complete paired games**. The 95% interval is **47.727–56.273%**. It passes the registered provisional point rule. Strict promotion is not confirmed. E81 becomes the research model; E56 remains the confirmed champion.

The teacher uses frozen E68 Gumbel800, no root noise, and chosen-action labels. A separate frozen E68 Gumbel128 actor supplies states. All 277,788 fresh training positions and 55,476 development positions have exactly the same setup, input, legal mask and outcome as E74. An E68 replay shard adds 55,832 rows for 333,620 training rows. Teacher noise and target construction change together, as registered; their individual effects are not isolated.

The fast 142,406-parameter bootstrap model uses the same training recipe, seed800000016, and selects epoch8 of10. Held-out policy CE falls from1.72035 to1.69131; outcome Brier falls from0.216040 to0.215713. Training takes106.65 seconds and the arena takes47.33 seconds. Full cycle time is1,235.33 seconds, including full matched re-labeling and development collection. All collection games complete. Native parity passes.

Native model:`e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8`.
Checkpoint:`84b70dcba91b0870ef23e8944f9ff214c0d29662a11849021c2108795eb033d1`.

The first-shard label diagnostic shows50.69% agreement between the old noisy-policy argmax and the verified no-noise teacher action. The old target assigns less than10% mass to that action on37.68% of positions. This is a diagnostic on identical states, not a strength estimate.

All sources, hashes, models, raw gate records and decisions are preserved. Full datasets remain under ignored local/research/e81. All113 release tests and strict Clippy pass. The restartable flywheel now accepts --teacher-action-targets. Its separate8-game train/8-game dev/one-epoch/16-game arena integration passes collection, training, export, parity and screening; it retains its local baseline. This small integration is execution validation only. Its local 'champion' is its initial E68 model, not the repository champion.

E82 repeats the repaired cycle from E81. E83 runs a separate fixed20,000-game champion milestone. Neither result is used to select an intermediate E81 checkpoint. No external best-in-class claim is made.
