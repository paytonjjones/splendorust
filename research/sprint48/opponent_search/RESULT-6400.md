# Matched-search-budget AlphaZero result

This is a separate diagnostic from the promoted AlphaZero800 campaign.

Splendorust PUCT6400 was compared with the pinned AlphaZero checkpoint while
the active AlphaZero search budget was also set to 6,400 simulations. The
checkpoint file still declares its original 800-simulation setting; the runner
overrode the active MCTS budget for this diagnostic and recorded both values.

| Measure | Result |
| --- | ---: |
| Requested games | 1,000 |
| Completed games | 1,000 |
| Paired setup blocks | 500 |
| Splendorust win credit | 58.85% |
| Paired bootstrap 95% interval | 55.75%–61.90% |
| Conservative Hoeffding 95% interval | 52.78%–64.92% |
| Replay-checked transitions | 56,056 |
| Terminal outcomes | 1,000 native scores |

The result is positive evidence at a matched simulation budget. It does not
pass the campaign's decisive-strength gate because the conservative lower
bound is below 55%. Fixed simulation counts are not equal total compute: the
models, implementations, information access, and native search behavior
differ. The benchmark also uses the pinned native AlphaZero rules profile, not
the canonical Splendor rules profile.

The original scheduler exited with status 2 after consuming the reserved seed
range. Recovery validated the retained games without rerunning them. The
recovered raw record set has SHA-256
`22022e9c2391ea3bece99a2864723b51e116635ab376c79bb33b7a22d698a053`.

The full recovery metadata is in `RESULT-6400.json`. The promoted result is
still the separate 77.5% / 1,000-game AlphaZero800 campaign in
`../RESULTS.md` and `../FINAL_DECISION.json`.
