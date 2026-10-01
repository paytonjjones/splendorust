# E79: current teacher against pinned native AlphaZero

Frozen E68 Gumbel800 scores **38.625%** against the pinned AlphaZero800 opponent in **2,000 complete paired games**. The paired bootstrap95% interval is36.60–40.725%; the conservative Hoeffding interval is34.330–42.920%. These results do not meet the strength goal. The old E56 PUCT800 result was37.775% on a different2,000-game schedule; this is not a paired comparison or evidence of a significant gain over that result.

Profile: `alphazero-native-32a27ac-v1`, native referee and unchanged upstream revision `32a27ac1f85d5de2766cc5f60c2bf04e557f7836`. E68 uses public observations, three sampled worlds,800 simulations,depth16 and noise0. AlphaZero retains its native true private reservation/deck-membership input. No equal-information or canonical global rank is claimed. Native cap terminals remain legitimate native-profile results. E56 remains the confirmed champion; E68 remains the research model.

All raw states/actions/chance streams/public-input hashes/rewards, eight shard logs, merged records, commands, source snapshots and metadata hashes are preserved. The model is `d199a3878d7feebb443cb8e01e4afee502e05f2e9ba34c7a042a6bb3b62b86f2`. The harness's historical seat label `champion` identifies the supplied E68 player here; it does not promote E68 to confirmed champion.

Wall time is938.02s with eight workers, concurrent with E78 screening and E80 diagnostics. This is a shared-host measurement. The native policy binary and metadata worker are also frozen under ignored local/research/e79. Full history replay validation is pending in the initial report and will be recorded when complete.

Paradigm reassessment: internal E76 proves a useful teacher/student planning gap, but this external result shows that the current teacher is not sufficient for the final strength goal. E80 identifies a concrete target defect and E81 tests its repair. If verified-action distillation still does not improve the fast model, further volume/capacity sweeps on these same targets have weak support. The next change must address teacher quality or model generalization directly, with an explicit diagnostic.

Full history replay passed: all 2,000 games and 111,760 transitions match their saved native actions, seeded chance draws, state hashes, public-input hashes, scores and terminal rewards. This checks saved execution; it is not an independent proof of upstream rules or a policy rerun.
