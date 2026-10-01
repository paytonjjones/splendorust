# E89: continued attention lineage

Retain E88 as the provisional lineage and E81 as the confirmed champion. E89 scored 47.6% against E88 in 2,000 completed paired root-only Gumbel128 games. The conservative 95% interval is 43.3194–51.8806%. Neither selection rule advances E89. The conditional champion comparison was therefore not run.

All 5,000 training games and 1,000 development games completed. Fresh data plus one fixed E87 replay shard gave 334,260 training positions and 55,782 development positions. The E88 teacher controlled whole games at 800 simulations, with no Gumbel noise and selected-action labels. Public-context sidecars, data hashes, raw collection records, model bytes and sources are preserved.

Ten training epochs took 507.66 seconds. Selection chose epoch 3. Development policy loss changed from 1.577324 to 1.576067; outcome Brier error changed from 0.205826 to 0.205734. Small development improvements did not transfer to the arena. The initial continued export exactly reproduces E88. The E81 base stays fixed.

Native parity passed on 64 real inputs: maximum logit error 0.00001717 and policy/value error 0.00000161. The shared-host root-cost median was 1.148886 times E81, within the 1.15 limit. The first timing ratio was 1.94377; all timings remain recorded, and these are not isolated speed claims. All 118 release tests, strict Clippy, and both legacy collector byte hashes passed.

The full cycle took 1,849.94 seconds (30.83 minutes), including shared-host load. No new champion or external strength claim follows from this run. GitHub Actions stays disabled; checks ran locally.

The next step is to test label stability directly. Existing E80 records show only 41.38% pairwise agreement between independent noise-free teachers on ordinary fixed observations, despite 89.66% within-teacher selected-action versus policy-argmax agreement. Those are different measures. E90 will measure independent chosen-action stability with the current E88 teacher on fresh learner-visited observations before further data scaling or architecture changes.
