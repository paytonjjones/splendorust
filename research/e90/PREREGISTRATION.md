# E90: teacher action-label stability

Hypothesis: Independent search worlds produce inconsistent selected-action labels even with Gumbel noise set to zero. This can limit distillation into a deterministic public-root model. The prior E80 records show low agreement between independent chosen actions; their reported policy-argmax agreement measures a different question.

Use frozen E88. Capture every second Main observation, at most 32 per game, from eight fresh E88 root-Gumbel128 trajectories at setup seeds 4770000000 through 4770000007. No forced blind reservations. Each captured public observation gets eight independent root-Gumbel800 searches and eight independent root-Gumbel128 searches, all depth 16 and noise zero. Preserve chosen actions, complete policy vectors, chosen-action values, legal actions, public contexts, and native root priors. Validate native root outputs across eight independent encodings of the same observation.

Measure pairwise chosen-action agreement, four-versus-four consensus agreement, chosen-action target entropy, and value variation. Report blind and known subsets separately, without claiming representative corpus prevalence. Compare the public root prior's action to the empirical eight-search action distribution. Use these observations only for diagnosis, not model training, checkpoint selection, or promotion. Keep all raw records and seeds.

If pairwise action agreement is below 75%, test whether a consensus teacher improves actual playing strength before spending more wall time on repeated single-action training labels. If agreement is high, measure train/development fit to search decisions before changing capacity again. A noisy target alone does not prove the cause of a learning failure or that a consensus teacher is stronger.
