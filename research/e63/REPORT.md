# E63: residual capacity result

The larger model scores 51.20% against E59 at 128 simulations in 2,000
complete games (95% interval 47.01–55.39%). This gain is unconfirmed.
At the measured cost budget of 64 simulations, it scores 41.525% in 2,000
complete games (37.25–45.80%). Keep E59 for the fast learning loop.
E56 remains the confirmed champion.

Training uses 336,989 rows and selects epoch 3 of 20. It takes 211.69 seconds.
Held-out policy KL falls from 0.5850 to 0.5735. Value Brier changes from
0.21564 to 0.21594. Base weights and normalization buffers remain exactly
fixed. Native/Python maximum policy/value error is below 0.000002.

Three timing runs use the same 568 observations and alternate order. E59 at
128 simulations takes a median 4.468 ms per decision. The larger model at
128 takes 8.467 ms; at 64 it takes 4.403 ms. The largest tested multiple of
eight within 1.05 times baseline cost is 64. This choice is saved before
arena outcomes. Timings are specific to this host and workload. Both models
use depth 16. All hashes, raw records, source snapshots, models, and failures
are preserved. Total training, timing, and two screens take 537.68 seconds.

This tested larger model does not improve strength per measured cost.
It does not establish a universal capacity limit. The next cycle uses fresh
800-simulation targets from E59 with full replay and the fast architecture.
