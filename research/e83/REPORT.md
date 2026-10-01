# E83: combined model/search champion milestone

**E81 Gumbel128 scores 54.8625% against E56 PUCT128 in 20,000 complete paired games.** The two-sided 95% empirical Bernstein interval is **53.720–56.005%**. The lower bound exceeds the registered 51% threshold. scripts/promote.py returns promote. Update CHAMPION.json to the frozen E81 model and Gumbel search profile.

Both players use 128 simulations and depth16. This confirms their combined model/search difference in canonical SplendoRust v2; it does not isolate the contribution of E81 weights from Gumbel planning. All seeds, models and budgets were fixed before play. There are no blocked or capped games. Raw report and record-set hashes are in gate/decision.json. The previous champion is preserved in previous-champion.json.

The milestone took 1,266.95 seconds with eight threads, concurrent E82 collection and E84 training. Process priority was lowered to nice10 during the fixed-budget run to favor the learning loop. This does not change statistical settings. The milestone did not choose E82 or E84 checkpoints and was outside their selection logic.

Confirmed native model hash: e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8. Search: flywheel-gumbel, three worlds, maximum16 root candidates, cvisit50, cscale0.1, no root noise.

This is an internal champion confirmation. External best-in-class strength is still unestablished; E79 records a remaining deficit against the pinned native AlphaZero target.
