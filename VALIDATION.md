# Validation

The engine implements base Splendor for 2–4 players. Tests and external
comparisons check its behavior. They do not prove that every possible state is
correct or that every legal game finishes.

## Rule choices

The engine uses all 90 cards and 10 nobles. See [Data sources](data/SOURCES.md)
for the publisher rules and dataset sources.

- Take three different colors if at least three colors are available. Take
  fewer only if fewer colors remain. A double take requires at least four
  tokens in that pile.
- Keep at most ten tokens after a turn. Return exactly the excess. You can
  return old tokens, newly taken tokens, or gold.
- Gold can replace a matching colored token even if the player has that token.
  The engine keeps all legal payment choices.
- Keep at most three reservations. Other players know visible reserved cards;
  blind reservations reveal only their count and tier.
- Nobles require permanent bonuses. They do not consume those bonuses. Take
  one eligible noble each turn. If several qualify, choose exactly one.
  A take or reserve turn can also gain an already eligible noble.
- A complete turn that reaches 15 prestige starts the final round. Finish the
  round so that all players have equal turns.
- Rank by prestige, then by fewer purchased cards. Exact ties share victory.
  Reserved cards do not break ties.

## Games that do not finish

A legal position can have an empty colored bank, three reservations, and no
affordable card. Gold may remain, but the player cannot take it without a
reservation. The printed rules give no pass action or winner for this case.
The arena records `no_legal_action` and gives no winner.

Legal token takes and returns can also repeat. If the arena reaches its
decision cap, it records `decision_limit` and gives no winner. Agent checks
avoid some known blocks; they do not guarantee completion.

The promotion policy permits at most 1% no-action games per stage by default.
It keeps every requested game and seat rotation. Unknown outcomes count as
zero candidate credit for the lower bound and one for the upper bound. The
bound must still pass the promotion margin. Any decision-limit game, execution
error, invalid evidence, or excessive no-action count rejects the stage.

Use `--max-no-action-fraction 0` with `scripts/promote.py` to require complete
games. Old decisions keep the policy that applied when they were made.
See [the policy record](docs/history/EXPERIMENTS.md#p2--conservative-promotion-with-rare-no-action-outcomes).

## What is checked

| Area | Checks |
| --- | --- |
| Rules | Main actions, payments, returns, reservations, nobles, deck exhaustion, final rounds, and ties. |
| State | All cards occur exactly once; tokens are conserved; scores, bonuses, ownership, and decision phases agree. |
| Legal actions | Every generated action at sampled states is applied to a copy and checked. Independent enumerators check payment and return choices. |
| Bad inputs | Invalid actions leave state unchanged. Invalid observations are rejected. |
| Hidden information | Opponent blind cards are redacted. Sampled states reproduce the input observation. |
| Replay | Seeded histories, saved actions, engine versions, and final snapshots agree. |
| Execution | Fixed-budget serial and parallel records agree. Sampled core operations allocate no heap memory. |

The [independent reference comparison](docs/PARITY.md) checks shared rules
against a pinned external engine. It also records excluded rules, private
information differences, and known reference defects. This is partial parity,
not proof that the engines are equivalent.

A historical 1,700-game check matched records on ARM macOS, x86 macOS under
Rosetta, and ARM Linux. That result applies to those seeds, settings, and
builds. It is not a general floating point portability guarantee.
See [the validation history](docs/history/VALIDATION.md).

## Run local checks

Run from the repository root with the pinned toolchain and lockfile:

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features --release --locked -- -D warnings
cargo test --workspace --release --locked
cargo test --workspace --all-features --release --locked
python3 -m unittest discover -s scripts -p 'test_*.py'
```

The Python suite skips optional reference tests unless `SPLENDOR_REFERENCE`
points to the pinned reference checkout. Use the
[reference setup instructions](docs/PARITY.md#reproduce).
GitHub Actions is disabled. Run checks locally and record which checks ran.
Do not present a skipped reference check as a pass.

## Check a report

```sh
cargo run --release --locked -- verify-report comparison.json
```

This command requires the report's engine version, source fingerprint, and
structured run settings to match. It reruns fixed-budget games and compares
ordered records, including blocked and capped records. It rejects timed runs.
It does not check elapsed times or statistical summaries. Older reports without
structured settings cannot use this command.

`scripts/promote.py` checks stage settings, seat rotations, seed schedules,
source identity, and completion counts. It computes the interval from the
records and checks the promotion rule. It records source, binary, report,
and tool hashes. A consistent report is not proof that arbitrary supplied
records came from a real run; keep execution and replay evidence too.

## Engine version and resource limit

The current engine is `splendorust-v2`. At `turns == u32::MAX`, a legal action
returns `TurnLimit` without changing state. An illegal action still returns
`IllegalAction`. Legal enumeration stays complete. A turn that reaches the
limit can still end the game normally.

Old v1 histories require the matching v1 source. Current fixtures have separate
v2 labels and validation records. Never relabel old evidence as a current run.
See [the version record](docs/history/VALIDATION.md#version-2-resource-limit-contract).
