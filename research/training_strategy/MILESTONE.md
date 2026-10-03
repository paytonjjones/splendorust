# Milestone rule and second-generation cost reference

This rule is registered before the first study has produced any trained model
or strength result. It adds no trunk or search change.

Add one second-generation comparison: frozen-teacher continuation versus the
original Entity, master 5465000000, 2,000 paired canonical games. Use the same
Gumbel 128, depth 16, world pool 3 and 32 workers as the other comparisons.
This is needed to measure the strength per compute of both second-generation
arms. Do not infer this result from two comparisons with different opponents.

Before any trained model or strength result exists, extend endpoint selection
to include the controlled PCR fit registered in `EFFICIENCY.md`. After all
three studies finish, consider the three first-generation arms, the iterative
and frozen-teacher second-generation arms, and PCR. Each must have a direct
comparison against the original Entity. Keep its raw records and model fixed.
An endpoint is eligible for the major-gain milestone only if all 2,000 games
complete, candidate credit is at least 60%, and its lower 95% bound exceeds 51%.
Choose the eligible endpoint with the highest candidate credit. Ties use the
fixed order: onehot, visits, visits-q, iterative, frozen, pcr. This selection is
conditional on the tested recipes; it is not an architecture or external rank.

Run scripts/promote.py with a fresh 2,000-game screen at master 5470000000
and a 20,000-game confirmation at the tool's separate master 6470000000.
Both agents use the frozen Gumbel 128 evaluation profile. Keep the tool's
validity and regression guards. If it stops confirmation, retain that result.
Do not run replacement seeds to get a favorable decision.

A confirmed major gain requires all confirmation games to complete, at least
60% confirmation credit, and a lower 95% bound above 51%. A smaller confirmed
gain is reported as smaller. Do not change official champion pointers.

If no endpoint meets the milestone condition, report that no major gain was
supported by these controlled experiments. This does not prove that all
AlphaZero training recipes fail. Inspect teacher quality, label coverage,
held-out errors, iterative controls and measured cost before the next change.
Efficiency controls remain part of the full study when needed for practical
self-play. Do not mark the goal complete while those required controls,
result checks, artifact archives, cost report or final handoff are unfinished.
