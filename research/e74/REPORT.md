# Full-volume Gumbel teacher cycle

Retain E68. The trained candidate scored50.025% against its parent with Gumbel128
for both models in2,000 fresh complete paired games (95% CI45.70–54.35%).
No blocked or capped games occurred. The provisional point rule and strict
promotion both retain the parent. E56 stays the confirmed champion.

Collected5,000 Gumbel128 actor games, labelled by independent noisy Gumbel800:
277,788 positions,all games complete. Development1,000 games/55,476 positions,
also complete. One prior1,000-game shard adds55,832 replay positions for333,620
training rows. Warm E68,10epochs,seed800000014; selected epoch8. Model142,406
parameters, native SHA9bf25b1459dc8a93539ccad90b832e071a4cf9f436d82ea3dd1f3fba50f9d726.

Training data collection900.06s; development203.75s; fitting108.17s; screen48.17s.
Whole cycle1,273.10s on the shared host. PyTorch/native parity passed. All sources,
models, hashes, raw records, labels and negative checks are preserved. Data is
under local/research/e74; per-shard hashes identify it.

New labels are sharp (development entropy0.4501,max target probability0.8312).
The selected model agrees with their largest action39.18%; train/dev KL1.4744/
1.4971. The small fit gap does not identify capacity, optimization, target noise
or teacher strength. This full-volume run did not compress a measurable gain.
First verify Gumbel800 teacher strength against Gumbel128 before another capacity
change. E73's search-only gain remains provisional; this is a negative learning
result and is not a public rank claim.
