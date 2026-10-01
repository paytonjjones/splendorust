# E65: native AlphaZero search-budget pilot

Frozen E56 at 800 simulations scores 38.25% against the unchanged external
AlphaZero at 800 in 400 complete games (paired bootstrap interval 33.75–42.75%).
All 400 histories and native transitions pass exact replay checks. No game is
unsupported, blocked, capped, or assigned an invented result.

This uses alphazero-native-32a27ac-v1 from evaluator commit 9c354b6. The referee
uses pinned AlphaZero source 32a27ac. Its native return, pass, noble, payment,
and turn-cap rules differ from canonical Splendor. The external agent retains
its private reservation and deck-membership information; SplendoRust receives
public observations. No canonical or global ranking follows from this pilot.

Candidate policy time totals 411.74 seconds and external time totals 1083.39
seconds on paired full-turn games. Fixed simulations are not equal cost.
Shared-host total runtime is 438.00 seconds. E66 tests a fixed cost-derived
2048-simulation budget on fresh games and checks its realized cost.

All model/source/binary hashes, raw records, source snapshots, profile rules,
and replay evidence are saved. The archive-copy name fix affects only saved
driver files; the active diagnostic executes the unchanged evaluator harness.
The exact original driver and its registered hash are also saved.
