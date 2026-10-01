# E66: cost-derived native budget pilot

Frozen E56 at 2,048 simulations scores 40.375% against unchanged AlphaZero at
800 in 400 complete native games. The paired bootstrap interval is 35.875–45.0%.
All 400 native histories pass exact replay checks. No global or canonical rank
is established.

The fixed budget is derived from E65 timing before these outcomes. Realized
candidate policy time totals 1,006.85 seconds versus external 856.96 seconds,
so the prediction exceeds equal cost by 17.5%. Do not call this an equal-cost
comparison. Total shared-host runtime is 496.94 seconds.

Both this result and E65 use AlphaZero's native rules and retain its private
reservation/deck-membership information. SplendoRust uses public observations.
More search did not close the native-profile deficit. Core rules, canonical
search defaults, model weights, champion, and research lineage are unchanged.
All sources, hashes, raw games, and replay evidence are saved here.
