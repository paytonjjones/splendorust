# Active 48-hour campaign

The campaign started at **2026-10-03 19:35:52 UTC**. Its fixed deadline is
**2026-10-05 19:35:52 UTC**. `RUN.json` records the live stage and consumed
masters. The final master remains sealed. No decisive win is established.

Current state: trial04 completed at 58.59375% exploratory win credit. This
promising point estimate does not establish a decisive win. Branch2 source
collection is the next GPU job; fitting has not started. The GPU queue has
one owner and one primary job.

| Completed candidate | Games | Win credit | Scheduler seconds |
| --- | ---: | ---: | ---: |
| One-hot Gumbel128 | 128 | 45.703125% | 531.875 |
| One-hot policy only | 128 | 33.593750% | 91.745 |
| Refit01 PUCT1600, fresh worlds | 128 | 47.265625% | 1,543.928 |
| Refit01 Gumbel1600, fresh worlds | 128 | 38.281250% | 1,545.709 |
| Refit01 PUCT1600, three chance universes | 128 | 58.593750% | 1,495.633 |

These are separate exploratory schedules. Changed seeds and settings prevent
an isolated estimate of each change. No partial schedule outcomes are used.

Trials02 and03, including the failed zero-game launch, are retained in
`artifacts/development-02-03`. Manifest SHA256:
`127a12ebb86c7dba6be8b0d1df2cc6e3c0399e80cce5190bc80a3f10a5e51da7`.
A restore verified all 408 files. The archive notes the missing imported
campaign-context helper snapshot in these older trials. Recorded source maps,
raw games, replay results, frozen binaries and logs remain intact. The helper
is included in trial04's source snapshots.

The development records, source/executable copies, logs and pilot rows are
retained in `artifacts/development-00-01`. Manifest SHA256:
`d585eccf7455bebc6b3152b3efcba191952597d3fc8de983b49110fd02ab1148`.
A full restore verified all 160 files. Duplicate service checkpoint copies
are referenced to the verified core archive in `WEIGHTS_REFERENCES.json`.
After restore, check executable hashes and set their execute bits. Descriptors
retain old ports; export again for a new service.

## Development trial 01 preregistration

Hypothesis: the first model's Gumbel128 search helps beyond its copied policy.
Measure policy-only play from the **same one-hot checkpoint** against unchanged
AlphaZero800, on 128 fresh paired games. Master: `17701000000`. Candidate
iterations0, depth16, worlds3, Gumbel cap16 (the zero budget selects root
policy directly). Use the checked new frozen worker, CPU inference, batch32,
1ms delay and 16 game workers. Port19721. This CPU job may overlap the owned
MPS refit; there is still one GPU job. Record both elapsed and policy times.
Backend float differences mean this is a diagnostic comparison; it does not
prove exact CPU/MPS trajectory parity or establish a final strength claim.

Result: **33.59375% credit**, 128/128 complete native-score games, zero search
simulations and 3,556 inferences. Paired exploratory bootstrap:
**24.21875–42.96875%**. Conservative paired Hoeffding:
**16.617481–50.570019%**. No native caps or invalid games. Replay checked
7,112 transitions. Raw SHA256:
`6057499ebcd3b9f377c73e50590fba382663a3876b2c90bcb639556d00043215`.
Scheduler time: **91.745 seconds**; driver time including setup/checks:
108.335 seconds. Evidence: `local/research/sprint48/external-01`.

The point estimate is 12.109375 percentage points below trial00. Different
seeds and backend limit causal attribution, and the exploratory intervals
overlap. This is a reason to prioritize higher-budget search rather than a
policy-only final candidate. It does not establish a scaling gain from 8 to
16 workers because workload and backend also changed.

## Development trial 00

Hypothesis: the generation-one one-hot model's canonical improvement also
improves native play against unchanged AlphaZero800. Candidate checkpoint:
`ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb`.
Search: Gumbel128, depth16, three sampled worlds, prior root cap16. Runtime:
MPS, batch32, 1ms batch delay, eight game workers. Master: `17700000000`.

Result: **45.703125% win credit** in 128/128 complete native-score games.
There were no native caps or invalid games. The paired exploratory bootstrap
interval was **37.5–53.90625%**. The conservative paired Hoeffding interval
was **28.726856–62.679394%**; caps-as-unknown sensitivity is identical.
This screen does not show a win and does not prove a loss. Keep the model as
a candidate; do not promote it against AlphaZero from this result.

Trial00's first paired setup was later used for an offline labeling pilot.
It is now a training setup. Any model trained on that shard needs fresh
played evaluation; the trial00 result remains a record of the original model.

The scheduler took **531.875 seconds**. Across games, candidate policy time
was 3,789.256 seconds and AlphaZero policy time was 259.175 seconds. These
are summed concurrent times, not elapsed wall time. The service averaged
about 7.5 useful rows per fixed 32-row batch. The later 32-worker trial fills about 31 rows per fixed 32-row batch.
This improves service use under that workload; the changed model and search
prevent a controlled inference scaling claim.

Replay checked all 128 games and 7,140 transitions, including legal moves,
chance draws, state/public-observation digests, and terminal rewards.
Raw record SHA256:
`0d1fb4501178daf90b59249daf2084fa88950be672ad77ddbae6ac7464836cd5`.
Local evidence: `local/research/sprint48/external-00/{trial,summary,replay,evidence}.json`
and `arena/games.jsonl`. Sources and executable copies are retained beside
the records. The original build's source fingerprint is `584589a4db074b5e`.

## Development trial 02 preregistration

Hypothesis: the full-corpus refit plus PUCT1600 and fresh public worlds
improves native play beyond the initial Gumbel128 candidate. Use the refit's
registered selected `fit/model.pt`, including the parent if the selector
retains epoch0. Do not select an epoch from played games. This tests a
combined candidate; it cannot isolate the effects of refitting and search.

Fixed schedule: 128 games, master `17702000000`, 32 workers, MPS batch32,
1ms delay, port19722. Search: PUCT1600, depth32, world_pool0 (fresh public
determinization each simulation). The Gumbel root cap is inapplicable.
Use the checked binaries from `build-controls/release/examples`, copied
into the run before play. Start only after the refit and its owned process
group end. Measure complete-game throughput and resource use; do not run
another primary GPU job. Fixed AlphaZero800 is unchanged.

Thirty-two workers can fill the existing batch32 service better than eight.
The previous policy-only test does not establish this gain. The host has
14 CPU cores and 48GiB RAM; check actual memory/load during this new workload.

## Training branch 1

The campaign started training branch 1: a two-epoch warm start on the verified full expanded
corpus. The short public development check in `TRAINING_DIAGNOSTIC.md`
supports checking native-policy drift after the prior canonical-only fit.
The branch uses existing expert data; it adds no final or development-game
records to training. Select weights with the existing full-dev rule.

The refit started at **2026-10-03 20:01:01 UTC**. Driver PID98875 owns trainer
PID98876 and its process group. Receipts/logs: `local/research/sprint48/refit-01`;
weights/metrics: `refit-01/fit`. It is the sole primary MPS job. Initial full
development score: 2.31105742 (policy CE plus four times outcome Brier).

The two-epoch refit completed in **1,494.291 seconds** and selected epoch2:
checkpoint SHA256
`44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f`.
Full-dev selection score improved to **2.25979946**. Native policy CE:
1.33158387 → 1.27574740; native outcome Brier: 0.20561159 → 0.20844755.
Canonical policy CE: 1.64090033 → 1.57121035; outcome Brier:
0.20699360 → 0.20990177. Thus policy loss improved and terminal calibration
became slightly worse. These metrics do not establish playing strength.
Trial02 used this selected checkpoint and completed; see its result below.

The selected refit and its full logs are retained in `artifacts/refit-01`.
Manifest SHA256: `2ab30249d888edad292cabeb90b739aab998692e92ecd9e2f9ab169e75844365`.
A restore verified all seven files, including both checkpoint byte streams.

The CPU offline-labeling pilot replayed two games from one paired setup and
produced 54 public-input rows in 14.950 seconds of labeling/replay work. It
passed a sampled-hidden-world input invariance check. This proves the path
works on that setup; it establishes no training or strength gain. Shard:
`local/research/sprint48/dagger-train-pilot-00`. Its native low32 setup seed
is checked against all 32,000 existing training/development setup IDs.

Expose root width, depth and world sampling in the native runner, with frozen
executable paths and accepted-setting checks. After local checks and the
refit, test higher search budgets on fresh exploratory masters. AlphaZero's
source, checkpoint, private information and 800-simulation budget stay fixed.

The full trial00 offline-label job completed in **52.412 seconds** with eight
CPU workers. It produced 3,516 rows from 63 paired setups; the separate pilot
adds 54 rows from the remaining setup, for **3,570 rows / 64 setups**.
Registry SHA256: `1c5f138fce0b31946649133ba722cd318024c346a103570ccc55acc2e67d628c`.
This is training data; it adds no played strength evidence.

## Development trial 02 result

Result: **47.265625% credit**, 128/128 complete native-score games. No caps
or invalid games. Paired exploratory bootstrap: **39.0625–55.46875%**;
conservative paired Hoeffding: **30.289356–64.241894%**. This does not support
a decisive win or show a clear gain from the combined refit/search change.

Scheduler time: **1,543.928 seconds**; driver including setup and replay:
**1,558.031 seconds**. Search used 5,723,200 simulations and 5,463,526
inferences. Replay checked all 128 games and 7,154 transitions. Raw SHA256:
`e66192fdd05f3a721c33ba385e4f3c4501e6fa6a2d4fbd6e67880773711281b8`.
Evidence is in `local/research/sprint48/external-02`.

## Development trial 03 conditional preregistration

If completed trial02 does not support choosing PUCT1600 for confirmation,
compare the same refit checkpoint with **Gumbel1600, depth32, world_pool0,
root cap32**. Keep AlphaZero800 unchanged. The fixed schedule is 128 games,
master `17703000000`, MPS port19723. Use 64 game workers and fixed batch64
with 1ms delay to test higher GPU throughput. Bind the actual batch size in
receipts and check exported numeric parity before play. The different fixed
batch can change floating-point results, so this is a combined search/runtime
candidate comparison, not a strict isolated estimate of root-allocation effects.
Record complete-game wall time, service occupancy, memory and replay results.
Do not use partial trial02 or trial03 outcomes for a decision.

The trial00 label archive is `artifacts/dagger-trial00`. Manifest SHA256:
`f8cfcd70e157ad4ada6edf2d59c001f1fa08a36865265f5867fe6a57a701ed00`.
A restore verified all 63 files. These labels are retained but will stay out
of branch2's matched refit01-source collection.

Trial03's first launch failed before any game setup or output record. Its
64 logs are retained at `external-03`; `RUN.json.failed_attempts` records this
zero-game failure. The campaign-context call omitted ROOT. After fixing it,
two real E56 zero-search CLI games passed on a separate validation setup.
That setup is excluded from final evaluation. Retry the unchanged trial03
protocol and master in a new directory; no outcomes selected this retry.

## Development trial 03 result

The retry completed all 128 native-score games with **38.28125% credit**.
No caps or invalid games. Paired bootstrap: 30.46875–46.09375%; conservative
paired Hoeffding: 21.304981–55.257519%. Scheduler time: 1,545.709 seconds.
Batch64 with 64 workers did not give a useful complete-game time gain over
trial02's batch32 / 32 workers. Search and game length also differ, so this
is not an isolated batch scaling result. Evidence: `external-03-retry`.

## Development trial 04 preregistration

Hypothesis: fixed chance universes let PUCT spend more visits on deeper
branches rather than new random refills. Use the same selected refit01
checkpoint with PUCT1600, depth32, world_pool3 and **chance_universes3**.
The chance seeds come from the policy RNG, never the referee or hidden state.
This combines finite root worlds and finite chance universes; it does not
isolate those two effects. All real referee moves and AlphaZero800 stay fixed.

Fixed schedule: 128 games, master17704000000, 64 workers, MPS batch32,
1ms delay, port19724. Use newly checked copied binaries from `build-chance`.
Bind new source and executable hashes. Record simulations/inferences and
complete-game time. This remains exploration; final seeds stay sealed.

## Development trial 05 prospective preregistration

After trial04 ends and the new worker passes checks, test **dynamic FPU**
with the same selected refit01 checkpoint, PUCT1600, depth32, world_pool3,
chance_universes3, 64 workers, MPS batch32 and 1ms delay. Use 128 paired games,
master17705000000 and port19725. This changes the unvisited-action value
from a fixed network estimate to the existing pseudocount running value.
It matches the pinned upstream update formula in credit units; it does not
establish a gain before play. Keep all other search constants unchanged.
Use copied checked executables from a separate build target. Do not use
partial outcomes from trial04 to alter this protocol. Both trials are
exploration, and different fresh seeds limit causal comparison.

Branch2 is prospectively revised before collection to 10% DAgger loss and
90% existing base loss. Append 57 fresh-label rows to each 512-row base update,
keep all base exposures and update counts, and select by 90% full-dev plus
10% held-out DAgger-dev score. No DAgger source games, fit or selector outcomes
exist at the time of this decision. This tests a larger distribution change
than the earlier 5% proposal, with about 11% more examples per update.

## Development trial 04 result

All 128 games completed with native-score outcomes: **58.59375% win credit**.
No caps or invalid games. Paired exploratory bootstrap: 50.78125–66.40625%;
conservative paired Hoeffding: 41.617481–75.570019%. The point estimate is
promising, but it does not establish a decisive win. Keep finite chance
universes as a candidate for the next search comparison.

Scheduler time: 1,495.633 seconds. Search used 5,710,400 simulations and
5,178,709 inferences. Replay checked all 128 games and 7,138 transitions.
Raw SHA256: `ce3f2045477286595b71090e94d9a5b46174ca89432c94b3a49a2153818e89c7`.
This is a combined finite-world / finite-chance profile on new seeds. It does
not isolate either effect. Evidence: `local/research/sprint48/external-04`.

The root CPU RPC0 compatibility fixture passed for branch2's pinned old worker
under the current runner's accepted-setting check. The same excluded setup
was reused; no new game or strength outcome was produced. Branch2 source
collection is now launched at port19730, with 1,024 train and 256 dev games.
It is the sole primary GPU job. Its results are data, not a played promotion.

Trial04 is retained in `artifacts/development-04`. Manifest SHA256:
`56f699cbaf0ffc8e44f15e73178f6259c6ba0921d7e2df7b80a81faaddcc582b`.
A full restore verified 185 files, including all raw/replay records, source
snapshots and binary byte streams. The duplicate selected checkpoint is
referenced to `artifacts/refit-01`.

The trial02/03 archive checkpoint locator was corrected from
`refit-01/fit/model.pt` to the actual refit archive entry `refit/fit/model.pt`.
Only the generated reference file changed. Repacking and full restore verified
all 408 files again; raw evidence and executable/checkpoint bytes did not change.
