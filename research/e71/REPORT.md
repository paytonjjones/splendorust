# Matched public-information distillation

Result: retain E68. The candidate scored 49.70% in 2,000 complete fresh paired
128-simulation games against E68 (paired 95% CI 45.37–54.03%). No blocked or
capped games occurred. Neither the provisional point gate nor strict promotion
passed. E56 remains the confirmed champion.

The experiment reused E68's 334,810 training rows, 55,860 development rows,
original E59 initialization, seed 800000013, 10 epochs, batch 1024, learning
rate 1e-4, optimizer, labels and selection. Only seven public context fields were
added, with 56 new zero weights. Selected epoch: 10. Model: 142,462 parameters.
Training, parity, screen and fit diagnostics took 176.93s on the shared host.

Development policy KL changed from 0.61236786 to 0.61235504, and outcome Brier
from 0.21466233 to 0.21464494. These changes are very small. Native parity passed
(max masked-policy/value error 1.43e-6). All raw screen records, hashes,
checkpoints, code snapshots, plans and failed experiments are preserved.

The information omission is proven, but this input extension did not establish
a playing-strength gain or identify that omission as the plateau cause. Do not
promote the candidate or infer capacity limits from this result. Keep the useful
input and collection infrastructure for future representation work.
