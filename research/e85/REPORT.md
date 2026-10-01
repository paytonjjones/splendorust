# E85: public-belief root input

Decision: retain E81. The frozen E81 network with mean input only at the root scored50.4% among1,999 completed games in the2,000-game paired screen. One game did not complete; the strict gate rejects the run. Do not count the incomplete game as a win. Either possible result remains below the provisional50.5% selection threshold.

Across452 observations and8 sampled worlds each, the392-float mean input and519-float public input were exactly invariant. Python, scalar Rust and batched NumPy matched exactly on3,616 rows. A small-pool test also matched exhaustive first moments. With blind reservations, the frozen network had mean unmasked81-output policy total variation0.10177 and maximum0.61204 across samples; mean input removed this variation. This is a network diagnostic, not a claim of improved full-search decisions.

The alternating568-observation cost check used identical128-simulation budgets and identical simulation/inference counts. The median cost ratio was1.00452 on the shared host. Legacy PUCT and noisy-Gumbel teacher files retained their exact reference hashes. Strict workspace Clippy and all117 release tests passed through the corrected gate.

An initial factory error forced800 simulations for the new agent name. That run finished before the stop command and is preserved underinvalid-budget-gate. It is invalid for this experiment. No champion or lineage was changed. The factory now shares an explicit budget helper with a regression test. Failed development checks are also preserved. The valid screen is undergate.

NN(mean features) differs from a mean of NN predictions. The next experiment will learn from the invariant public input using the existing teacher labels, rather than treat the frozen-network result as a test of trained belief encoding.
