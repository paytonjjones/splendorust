# E64: fresh lineage-teacher cycle

The candidate scores 49.475% against E59 in 2,000 complete games at the same
128-simulation budget (95% interval 45.31–53.64%). Retain E59. E56 remains
the confirmed champion.

The E59 teacher uses 800 simulations to collect 1,000 fresh training games
(55,990 positions) and 1,000 independent development games (56,072 positions).
All collection games complete. Training adds the E58 5,000-game replay corpus
for 336,941 rows. The normal bootstrap model selects epoch 6 of 10. Its native
SHA256 is 27c41fc19a6ee51c469b816d44d1e3ea90b66d325ece519f2346a5d047fdb3c1.

Collection takes 233.65 and 265.37 seconds. Training takes 218.30 seconds,
and screening takes 83.31 seconds. Total cycle time is 809.07 seconds under
concurrent evaluator and E65 workloads. These are shared-host times; do not
compare them as isolated throughput regressions. Native/Python parity passes.
All source snapshots, models, setup seeds, corpus hashes, and raw gate records
are preserved. Fresh large binary corpora remain under ignored local/research/e64.

This normal fresh-data cycle did not improve playing strength. A single
negative screen does not prove that further teacher data cannot help.
