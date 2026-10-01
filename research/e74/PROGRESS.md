# Gumbel model learning in progress

The preregistered5,000/1,000-game cycle is active. E68 with Gumbel128 generates
states; an independent noisy Gumbel800 teacher produces completed-Q labels.
One prior1,000-game shard is replayed. The next2,000-game screen uses Gumbel
for both models, so it measures a learned change. E56 stays champion.

Integration runs verify context sidecars, training, native parity, candidate
model loading and the Gumbel arena profile. Their16-game results are execution
checks,not strength evidence. The first check selected epoch0 with a different
context header despite identical function; preserve that check as invalid for
model selection. The runner now skips that case. A zero-epoch run verifies the
skip; another trained one-epoch check exercises the candidate arena path.

All plans, source snapshots and complete-shard records are preserved. Raw data
stays under local/research/e74 with file hashes. Do not interpret unfinished
collection or the integration checks as a model improvement.

external-baseline.json records the evaluator's completed frozen E56 native
results (producer db43fe3):23.395% at128 over20k and37.775% at800 over2k.
These native-rule and unequal-information results do not establish canonical
rank. They show that the stated strength goal is still unmet.
