# Independent engine comparison

Checked on 2026-09-25 against `roeey777/Splendor-AI`, commit
`95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b`:
https://github.com/roeey777/Splendor-AI/tree/95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b

The checkout has an MIT license (copyright 2024 roeey777). The harness checks the
commit, tracked-file status, and license before import. It records the license
SHA-256. No external implementation code is copied into this repository. The
optional audit imports the reference rule modules from a separate checkout.
It needs only Python's standard library; it does not install or import the
reference's ML dependencies.

## Checked scope

The functional data matches all 90 cards and all 10 nobles after color and ID
normalization. For each sampled complete turn, the harness constructs the
reference state from a privileged test snapshot, checks that the compound
turn is in the reference legal-action list, applies it through `update`, and
compares tokens, purchased and reserved cards, bonuses, points, nobles, market,
deck counts, next seat, and normal end timing.

The reference draws from independently shuffled decks. The harness aligns the
single replacement draw before a turn. It does not compare RNGs or assert that
unknown deck orders match. State construction uses each player's own observation
to recover private reservations for the test. This data never goes to an agent.
The harness compares a turn in isolation; it does not feed one reference result
into the next case. Thus the result is transition parity on the stated shared
cases, not full engine equivalence.

The first fixed workload uses 20 games per player count (2, 3, 4), alternating
strong and random policies, seed 92,000,000 plus player count times 1,000,000
plus game index. Each game stops at normal termination, a blocked state, or
1,000 complete turns. The exporter does not award wins to stopped games.

Result: **5,016 matched turns**, including **130 noble acquisitions** and
**52 normal end transitions**. Exclusions: 90 blind reservations, 298 returns
of a collected color, and 64 optional gold payments. These are counted, not
silently removed. The summary includes source, exporter, harness, license,
and case-file identifiers. The compressed cases preserve the exact inputs.

## Complete action sets

A second export of the same workload enumerates every complete-turn path at
every tenth turn, plus each blocked position. This includes payment, return,
and noble branches. After explicit rule-difference filters, both engines have
exactly the same **10,258 shared choices at 574 positions**. Two of these
positions have no local legal action; the reference offers a pass.

The local exclusions are 981 blind reservations, 288 optional gold payments,
and 5,046 returns of a collected color. The reference exclusions are 2,257
reduced takes and two passes. Counts refer to compound turn paths, so several
paths can start with the same main action. Duplicate shared paths fail the
check. Missing or extra shared choices also fail it. The seven-card limit is
an explicit filter but was not reached in this workload.

Evidence: `docs/results/reference-choices.summary.json` and its compressed
case file. Use a third exporter argument of `10` to reproduce this sampling.
An argument of `1` checks every visited position; `0` disables regular
choice sampling. Blocked states always include their empty choice set.
The optional tests also inject missing and duplicate choices.

## Differences and limits

The publisher's refreshed rules remain the rule authority:
https://cdn.svc.asmodee.net/production-asmodeeca/uploads/2022/01/SCSPL01EN_SPLENDOR_RULES_LIGHT.pdf

| Area | Reference behavior | Local behavior / audit scope |
|---|---|---|
| Blind reservations | No action | Supported; excluded from shared-turn check |
| Gold payment | Uses colored tokens first | Preserves optional gold use; those payments excluded |
| Token returns | Cannot return a collected color | Preserves every excess-return choice; those returns excluded |
| Reduced takes | Allows smaller takes near the hand limit | Local takes follow available-pile count; Shared full-turn choices checked after explicit filters |
| Bonus count | Blocks a purchase at exactly seven cards of that color | No such local cap; excluded if encountered |
| Nobles | Includes a choice in each compound action | Local pending phase or automatic single choice; compared after complete turns |
| No legal action | Adds pass, ends when all pass | Local engine reports unresolved rules gap, with no winner |
| Tiebreak | Minimum cards computed over all players | Local minimum is among tied leaders; outcome parity not claimed |
| Information | Full state and decks exposed; no private-information mask | Local agents receive redacted observations; information parity not claimed |
| Invalid actions | Successor assumes valid input | Local validation rejects invalid actions; error parity not claimed |
| RNG and replay | Different setup and history representation | Not compared |

An external engine can share a defect with the local engine. This comparison
supplements the publisher rule audit, invariant tests, and independent payment
and return enumerators. It does not replace them.

## Reproduce

```sh
git clone https://github.com/roeey777/Splendor-AI.git /tmp/splendor-reference
git -C /tmp/splendor-reference checkout 95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b
cargo run --release --locked --example parity_export -- 20 92000000 > /tmp/parity.jsonl
python3 scripts/check_reference.py --reference /tmp/splendor-reference \
  --cases /tmp/parity.jsonl --output /tmp/parity-summary.json
SPLENDOR_REFERENCE=/tmp/splendor-reference \
  python3 -m unittest discover -s scripts -p test_reference.py
```

The optional integration tests verify matches and exclusions, and ensure that
corrupt scores, bank counts, and deck partitions are detected. Ordinary Cargo
tests stay offline and do not require the reference checkout.
