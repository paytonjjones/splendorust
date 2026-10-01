# E89: compound the public-root research lineage

Hypothesis: E88 can distil further search strength when its own 800-simulation policy supplies fresh actions and full-game outcomes. Keep the E88 attention architecture and frozen E81 leaf/base. Start from the exact E88 checkpoint. Change the data generation model, not the architecture or search algorithm.

Collect 5,000 fresh full games at 800 simulations, depth 16, Gumbel noise 0, 14 threads, seed 4730000000. Collect 1,000 development games at 4740000000. Use selected-action targets, the original six-turn opening exploration, and public-context sidecars. Use the last E87 training shard as fixed replay. Cache the same exact public means/features as E88. Keep every unknown outcome explicit; do not invent a winner.

Train 10 epochs with AdamW learning rate 0.0001, batch 1024, seed 800000021, and outcome-development checkpoint selection. An unchanged checkpoint skips the arena. Require native parity, unchanged frozen base, and median native root-cost ratio at most 1.15 against E81 before the screen.

Screen 2,000 fresh paired root-only Gumbel128 games at seed 4750000000 against parent E88. Select the provisional lineage only if worst-case requested win credit exceeds 50.5%. Keep the strict promotion decision. Keep the champion E81 unchanged. If selected, use a separate 2,000-game check against E81 at 4760000000 to assess accumulated lineage progress. This diagnostic does not use the champion gate or establish an external rank. Reserve 20,000 games for a later milestone.

Allow the existing root-only Gumbel agent in the offline collector. Preserve default collector bytes, rules, RNG streams, labels, opening sampling, and runtime inputs. This enables use of the new lineage as a teacher; it does not change core rules.
