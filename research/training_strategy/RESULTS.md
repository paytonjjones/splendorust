# Entity training study: closed early

The user closed this study on 2026-10-03 because the remaining evaluation cost
was too high. The larger registered study is incomplete. Keep the simpler
training approach. No model was promoted.

## Training decision

One offline pass improved on frozen Entity: one-hot scored 56.325% in 2,000
complete games, with 95% interval 52.03–60.62%. Visits scored 56.05% against
original Entity, but direct visits/one-hot scored 49.45%, interval 45.21–53.69%.
It supports no adoption advantage for visit targets. Action-Q versus visits
scored 49.30–49.35%, interval 45.02–53.63%, with one unknown no-action outcome.
Extra Q supervision has no supported benefit here. Keep one-hot policy labels
and omit the extra Q head for now. These uncertain results do not prove
 equivalence or that richer labels can never help. The offline gain also
includes the shared root/terminal value update; policy loss is not isolated.

## Final exploratory result

Both second-generation four-epoch fits finished and selected epoch 1.
Iterative versus frozen-teacher continuation scored
50.1953% credit in 256/256 complete games;
95% interval 33.36–67.03%.
Master 5492000000; canonical Gumbel128/depth16/pool3; 64 workers;
runtime 505.67 seconds. The fixed 256-game closure check
was registered before its outcomes as exploratory. It supplies no supported
iterative advantage and does not establish equivalence. It does not replace
the five planned 2,000-game screens or compare either model with static or
original Entity. Lower frozen-arm held-out loss is not strength evidence.
Do not adopt iterative training from this sample. Preserve both fits for a
future controlled test. PCR, staging, noise, opening randomness and symmetry
remain untested. No major gain or external ranking is established.

## Data and costs

First train/dev have 2,000/400 completed, replayed games. Second iterative data
have 2,000 completed games. Frozen data have 1,999 complete games and one blocked
game: 46 unknown rows excluded, 111,241 eligible. Common development has 400
complete games and 22,192 eligible rows. All corpora passed label audits.
Collection seconds: first train/dev 8,865.911/2,129.709; second iterative/frozen
7,934.063/8,682.167; new dev 1,388.865. First fits took about 243 seconds each;
second fits took 408.693/403.604 seconds. Five first-stage screens took about
10.7 hours total. Generation and evaluation dominate cost, rather than fitting.
The excluded 64-worker pilot improved arena throughput 1.480 fold with exact
ordered-record parity. All timings are shared-host measurements.

FINAL_COST.json counts each actual command once and retains copied receipt
locations, resource-pilot cost and last logged service counters. Interrupted
first-stage commands, the adopted frozen collector and frozen fit lack
recoverable parent exit receipts; exit codes stay unknown. Collector/fit time
is retained separately. Service counters are lower bounds and are not added
to command elapsed time. Accumulated command time is not total host wall time
or isolated GPU cost. Unknown cost tails remain unknown.
The one-hot pass gained 6.325 credit points for roughly 3.12 hours of reported
train/dev/fit cost, about 2.0 points per production hour. This excludes setup,
pilots, evaluation and interrupted work, and is conditional on original Entity
at Gumbel128. No iterative/PCR strength-per-compute claim is supported.

CLOSED.json retains both selected weight hashes and fit metrics. The archive
retains all epochs, raw rows, histories, interrupted work, frozen source and
original executables. See HANDOFF.md and archive-verification.json. Official
champion weights and rules are unchanged. INTERIM_RESULTS.md retains history.
