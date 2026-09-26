# Validation and rule decisions

## Scope and authority

The implementation follows the publisher's base-game rules. The complete functional datasets are documented in [data/SOURCES.md](data/SOURCES.md). There are no expansions or copyrighted visual assets.

Tests cover setup for 2/3/4 players, each main action, bank exhaustion, double-take threshold, optional gold use, discounts, free purchases, reservations and the three-card cap, market refill/deck exhaustion, token returns, one noble per turn, noble choice, end-game timing, fewest-card ties, and shared victories.

The core property test branches over **every** generated legal action at each sampled state, applies it to a clone, and checks invariants. It also reconstructs hidden worlds and checks that the original observation is preserved. Independent Cartesian reference enumerators check the optimized payment and return generators. Invalid indices, payloads, and observations are tested for rejection without state mutation or panics. Observation validation rejects an opponent blind-reservation identity supplied by a caller, as well as inconsistent reservation counts. Such an identity cannot occur in the canonical redacted observation.

Invariants check the complete 90-card partition, every card's tier/location, compact reserved slots, all six token totals, hand limits including pending returns, derived score, derived bonuses, noble ownership/eligibility, and phase constraints. They also check seat/turn consistency, mandatory market refill, and a threshold score for a declared final round. All tokens, including gold, are conserved. Setup determines the total supply.

Reproducibility tests cover RNG golden values, seeded transitions, hidden-information redaction, agent choices, replay serialization, and identical serial/parallel game records. The test suite runs 10,000 seeded random trajectories with invariants after every decision. A separate large release audit is recorded in [docs/results/million-audit.txt](docs/results/million-audit.txt).

## No-action positions and nontermination

A reproducible random trajectory reaches a position with an empty colored bank, three active-player reservations, and no affordable card. Gold can remain in the bank, but it cannot be taken without reserving. This is a rules gap, not a negative-token or missing-card failure.

The printed rules do not define a forced pass or stalemate winner. We therefore stop and label the trajectory `no_legal_action`. We do **not** classify that position as a normal terminal state, award points-based wins, or silently drop it from comparison uncertainty. An all-random arena reaches these positions frequently. A regression test also shows that legal take-and-return turns can repeat forever. Thus, termination is a measured property of a policy/seed set, not a theorem about all legal play.

Normal-game results, no-action counts, and decision-limit counts must be reported separately. The promotion gate rejects a candidate when any game is unfinished. A future optional forced-pass ruleset would need its own version and experiments. It must not silently change this ground truth.

## Interpretations

- Take three distinct colors when at least three piles are available. Take fewer only when fewer colors remain. The newer publisher rules state this explicitly.
- Return exactly the excess above ten. Old or newly taken tokens, including gold, can be returned. No voluntary return below ten is added.
- Gold can replace a matching token that the player already has. All such payment choices are enumerated.
- Visible reservations remain known; blind reservations reveal only tier and count to other agents.
- Nobles use permanent bonuses only, do not consume them, and are mandatory. If more than one qualifies, the player chooses exactly one.
- Exact ties after prestige and fewest purchased cards share victory. Reserved cards are not an extra tiebreaker.
- A player can gain a noble on a take or reserve turn if the requirement was already met.

## Limits of the evidence

No external engine is used as an unquestioned oracle. A pinned MIT-licensed independent engine now matches 5,016 shared complete-turn transitions, 10,258 shared choices at 574 positions, and all 90 card / 10 noble tuples. [The comparison record](docs/PARITY.md) defines the workload, checks, exclusions, source, and license. The reference has material rule and information differences. This is bounded transition parity, not full engine equivalence. Earlier data sources include an unlicensed repository; no implementation code from it was copied. The local independent enumerators cover the largest combinatorial decisions.

No test suite proves all reachable states correct. The milestone is a tested foundation with explicit rule boundaries. Search strength has been measured against the included agents, not against expert humans. The core does not yet have a formal verification proof, external engine equivalence certificate, or tested cross-platform floating-point search guarantee.

## Report rerun checks

New reports contain `run_config`, including all search settings and an optional
precise duration. Serialization stays in the arena crate. `verify-report FILE`
requires a matching engine and source fingerprint, fixed budgets, valid run
settings, and agreement between structured settings and existing metadata. It
reruns the tournament and compares ordered game records exactly. Capped and
blocked records can pass this reproducibility check; they still cannot pass the
promotion gate. This command does not verify statistical summaries or timing.
Reports without structured settings remain readable and fail rerun verification
with an explicit error. Search equality across architectures remains untested.

Tests cover non-default search settings, all rollout/evaluation choices,
nanosecond duration preservation, unknown fields, changed game records,
inconsistent metadata, missing settings, source/version mismatch, timed runs,
and exact reproduction of capped records.
