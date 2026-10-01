# E86: learned public-belief root model

Decision: retain E81. The519-feature public-belief root correction scored48.15% against E81 Gumbel128 in2,000 complete paired games. The strict gate retains the baseline. The champion and research lineage stay unchanged.

Reconstructed all seven data files with exact saved setup/input/mask/outcome checks. Reused333,112 training positions and55,636 development positions; all teacher labels remained unchanged. Reconstruction took216.96 seconds and cached public-feature preparation took5.13 seconds. Batched NumPy matched Rust exactly on3,616 diagnostic rows.

The model has592,537 parameters, of which450,131 are trained. The E81 base/leaf weights remain exactly frozen. Twenty epochs took186.54 seconds; development selection chose epoch2. Initial development policy loss1.65071 fell to1.64379 at epoch2, then rose to1.83801 at epoch20. This is evidence of poor held-out fit after early training, not proof of its cause.

Initial and trained native export checks passed on64 real inputs: maximum logit error0.00001526; maximum policy/value error below0.0000016. The alternating568-observation trained cost median ratio was1.0130 on the shared host, with equal128-simulation work counts. Strict Clippy and all118 release tests passed. Tests cover public-input invariance, exact frozen leaf outputs, legal search, and one root correction per search.

The model format is SPBELF01 with an E81 bootstrap base and SPGATED3 correction on519 public features. Use the root-only search profileflywheel-root-gumbel-candidate (or explicit root_only=true). Cached911-float training sidecars contain392 mean features plus519 public features; they add no real hidden card, deck order or setup seed.

This negative result does not establish that sampled-world noise is harmless or that the model lacks capacity. It shows that this learned root correction did not convert the current off-policy teacher data into a stronger128-simulation agent. The next high-value test should improve trajectory/value targets rather than repeat capacity or encoding variants.
