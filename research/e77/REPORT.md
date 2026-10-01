# E77: large correction at the root

The model has 3,035,161 parameters, including 2,892,755 trainable correction parameters. The frozen E68 base serves all search leaves. The 384-wide, six-block RMSNorm/SwiGLU correction serves the root once per decision. Its zero-initialized head preserves the initial E68 function exactly.

Checks passed: initial PyTorch identity, frozen base, nonzero correction-head gradient, exact checkpoint reload, native inference parity on 64 real inputs, and identical actions, targets and work counts across 1,312 decisions in 16 complete games. A unit test checks one correction call per root and multiple base calls per decision, in both PUCT and Gumbel modes. Existing canonical PUCT and noisy Gumbel teacher corpora remain byte-exact. All 113 release workspace tests and strict Clippy passed.

Three alternating timing runs over 568 fixed Strong-game observations measured a median decision-cost ratio of 1.04249 versus E68 Gumbel128. This is a shared-host measurement of the initial model. Trained-model cost will also be measured before a lineage decision. The declared maximum is 1.15; a slower model requires a separate cost-matched screen.

Initial native hash: `a2ba3e95b5311f5da932d637da81dd91dcbb77571ab01b4eacea677076a8ac90`.

The initial test compile failed due to an incorrect counter name. The corrected test suite passed; both logs remain. Standalone timing compilation required Rust thin LTO to match the release dependencies. No rule, card, RNG or replay changes were made. E78 trains this structure on the fixed E74 corpus and uses fresh paired screening seeds. No strength gain is claimed by these checks.
