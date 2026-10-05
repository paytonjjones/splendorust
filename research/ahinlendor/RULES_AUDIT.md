# Canonical base Splendor rules audit

## Result

SplendoRust implements the published two-player base game for the checked
rules below. AhinLendor has the same card and noble content and matching
two-player end condition, but it has smaller action sets for payment and
returns. Keep SplendoRust as the referee. Do not hide these restrictions in
the adapter.

The primary source is the [Space Cowboys base-game rulebook (PDF)](https://cdn.svc.asmodee.net/production-spacecowboys/uploads/2025/10/SCSPL01EN_SPLENDOR_RULES_LIGHT.pdf), published from the [Space Cowboys Splendor page](https://www.spacecowboys-games.com/game/splendor/). The rulebook's setup and turn rules are on pages 1–2.

## Content and identity

The rulebook specifies 90 development cards in three tiers and 10 nobles.
SplendoRust stores 90 cards and 10 nobles in `crates/splendor-core/src/data.rs`;
`crates/splendor-core/src/tests.rs::static_data_complete_and_auditable`
checks the tier counts, colors, points, costs, and CSV identities. A read-only
comparison with AhinLendor `game_logic.cpp::standard_cards` finds all 90 card
records equal by tier, bonus color, points, and cost. Its card IDs are the
SplendoRust IDs plus one. Noble requirements are the same set, but their order
differs. Map canonical noble IDs 0–9 to AhinLendor IDs
`[9, 8, 10, 6, 7, 5, 4, 2, 3, 1]`. Check signatures before applying this map.

## Rule comparison

| Rule | Published rule | SplendoRust | AhinLendor and adapter effect |
|---|---|---|---|
| Setup | 90 cards, 10 nobles; in a two-player game, four of each colored token and five Gold | `GameState::new` uses these counts and deals four cards per tier (`lib.rs::new`; `tests.rs::setup_counts_and_supply`) | Same two-player counts and content (`game_logic.cpp::initializeGame`). Different RNGs mean setup orders must come from one shared raw fixture in performance tests. |
| Take tokens | Take three different colors, or two of one color only when at least four were available before the action; take fewer if fewer different colors are available | `legal_actions` and `apply_action` enforce these conditions | `validateTakeGemsMove` enforces the same threshold and distinct-color count. Map only matching TAKE actions. |
| Reserve | Reserve one visible card or the top card of a tier; take one Gold if available; maximum three reserved cards | `ReserveVisible` and `ReserveDeck` record public/private status, take Gold, and reject a fourth reservation (`lib.rs::reserve`; tests cover visible and blind reservations) | Same action and limit. Its `GameState` stores all reserved IDs. The bridge must build the actor's payload from the sanitized observation, never serialize the full referee state. |
| Buy and Gold | Pay a card's discounted cost; Gold is wild and may replace any color, even if the player has tokens of that color | Rust lists each valid colored payment in `Action::Pay`; Gold is the remaining cost (`legal_actions`, `apply_action`) | AhinLendor pays available colored tokens first, then Gold (`applyMove` BUY_CARD). This is a legal choice but not the full legal action set. Do not claim action parity for buys; the canonical referee resolves payment. |
| Token limit | At end of turn hold no more than 10 tokens; the player chooses which tokens to return | `Action::Return([u8; 6])` enumerates all choices, including Gold, and removes exactly the excess (`tests.rs::token_returns_allow_old_new_and_gold_tokens`) | AhinLendor returns one colored token at a time and rejects Gold returns (`validateReturnGemMove`; legal actions use colors only). This is a real rule/action-space gap. A referee adapter must permit the canonical choice and must not silently force colored-only returns. |
| Nobles | At most one eligible noble is claimed after the action; choose if more than one is eligible | Rust enters a Noble phase for multiple choices and auto-claims a single eligible noble (`after_tokens`; noble tests) | AhinLendor has explicit noble choice and auto-claims one eligible noble (`resolveNobleAndEndTurn`). Equivalent when choices are mapped by requirements. |
| End and ties | End after a player reaches 15 points at the end of the round, so each player has equal turns; most points wins, then fewer development cards; otherwise share the win | `end_turn` and `outcome` implement equal turns, 15 points, card-count tie break, and shared ranks (`lib.rs::end_turn`, `outcome`; tests cover final round and ties) | `isGameOver` waits for the same equal-turn boundary; `determineWinner` applies the same score/card-count tie break and draw. Seat 0 must have the same first-player role in both implementations. |
| No legal main action | The rulebook defines four actions but does not define a forced pass or a stalemate winner | Main phase can have no legal action; core does not invent a pass or outcome | AhinLendor exposes `PASS_TURN` when its action generator finds no regular action. Do not map this to a Rust victory. Preserve and report a no-action state under the registered completion policy. |

## Information boundary and adapter requirements

Rust `Observation` explicitly removes the identities of an opponent's blind
reservations and contains no seed or future deck order (`lib.rs::observe` and
the `Observation` type documentation). `Observation::determinize` assigns
unknown cards uniformly from the remaining tier pools; it does not infer an
opponent's past strategy (`lib.rs::Observation::determinize`).

AhinLendor's internal `GameState` contains exact deck order and all reserved
card identities (`game_logic.h::GameState`). Its state encoder masks an
opponent's blind reservation for the acting observer (`state_encoder.cpp`),
and its ISMCTS code samples hidden cards. The adapter must still construct its
root input from Rust's public observation, the actor's own reserved identities,
and public history. It must not pass a Rust raw-state dump, the true opponent
blind IDs, or future draw order to the agent. Verify this with two raw states
that differ only in those hidden fields and require identical adapter payloads.

Rust has explicit Payment, Return, and Noble phases. AhinLendor applies a buy
and its chosen payment atomically, and returns excess tokens as several
single-token actions. The adapter must keep these as substeps of one canonical
player turn. Search action counts and timing must report the different phase
and action semantics; a Rust `BuyVisible` transition is not one equivalent
transition to AhinLendor `BUY_CARD`.

For raw engine performance, use only supplied TAKE actions for the matched
one-step apply measurement. Test full logical turns or playouts separately,
with action and phase counts. Validate market, bank, player material, nobles,
card identity signatures, and current seat before accepting a shared fixture.

## Evidence paths

- Rust actions, phases, observation, legal actions, application, and terminal rules: `crates/splendor-core/src/lib.rs`.
- Rust card and noble data: `crates/splendor-core/src/data.rs`.
- Rust rule tests: `crates/splendor-core/src/tests.rs`.
- AhinLendor definitions and implementation: `local/strength/external/ahinlendor/game_logic.h` and `game_logic.cpp`.
- AhinLendor observer projection: `local/strength/external/ahinlendor/state_encoder.cpp`.
- AhinLendor sampled hidden-state search: `local/strength/external/ahinlendor/native_mcts.cpp`.
