# Rule and policy profiles for whole-game comparison

A profile is an explicit test contract. It is not a claim that all rule differences are ambiguous. Optional gold use, excess-token return choices, blind reservations, one chosen noble, and normal final-round victory are published-game requirements. A benchmark can use a policy that avoids some of these actions. A benchmark that changes these rules must use a separate profile and report a variant result.

The normal engine keeps the published-base rules. A benchmark feature or adapter must never select a compatibility profile by default. Record the profile ID, corpus hash, source fingerprint and exact policy with each result. Keep benchmark-profile checks separate from normal-rule regression tests.

## Implemented profiles

| ID | Rules and policy | Empty action set | Meaning |
|---|---|---|---|
| `published-base-v1` | Existing complete Splendorust rules in VALIDATION.md | Report `no_legal_action` when the full legal set is empty | Normal base-game engine result; descriptive ID for the default rules |
| `seal256-intersection-v1` | Published rules unchanged; restricted turn choices below | `profile_blocked` if published actions remain; otherwise `no_legal_action` | Implemented shared-corpus whole-game benchmark; no passes |

The measured intersection profile does not call the optional forced-pass API. The feature-gated forced-pass test interface is a separate explicit variant, allowed only when the actual canonical legal set is empty. Its version is separate from the normal engine. It is for tests of the unresolved no-action case, and it must not turn a blocked state into a published-rule victory. There is no measured `seal256-compatible-v1` forced-pass profile.

## Shared setup and state

The corpus generator compares complete functional card and noble multisets and stores native-to-canonical ID maps. A card tuple contains tier, bonus color, points and five costs. A noble tuple contains points and five requirements. A native numeric ID alone does not establish identity.

Each case injects the same ordered tier decks, ascending canonical noble IDs, first player, and separate policy seed. The first four cards of each tier become visible. The C++ adapter reverses the remaining native deck and draws its last element through the existing chance action. This matches the declared fixture draw order. Chance selection consumes no policy RNG. Market refill positions differ, so policy keys use canonical card identity and public snapshots sort market IDs. The policy does not select by native market position.

The normalized trace after each completed turn checks bank; both players' tokens, bonuses, scores and visible reserved-card IDs; visible market IDs; remaining deck counts; remaining noble IDs; active player; completed turns; and terminal status. The trace also compares the projected legal-action keys before every selection and the selected keys. Setup fixtures and selected/refill history determine acquired card identities. This is a summarized state trace, not a byte-for-byte comparison of hidden native state. It does not independently compare the complete remaining deck order or owned-noble identity on every turn. These are limits of the current gate.

No blind reservations occur, so the normalized trace does not expose an opponent's private reservation to the policy. Adapter fixture access remains separate from policy inputs. Use the same SplitMix64 bounded-index sampler for random action selection. Reusing a numeric seed with unrelated native shuffles would not be a paired setup.

## Exact implemented turn projection

At each main state, the list contains:

- Every affordable visible purchase, keyed by canonical card ID `0..89`.
- Every affordable reserved purchase, keyed by `100 + canonical card ID`.
- Every three-distinct-color take whose resulting hand is at most ten tokens.
- Every double-color take with at least four tokens in that bank pile, only when the hand has at most seven tokens.
- Every visible reservation that fits the three-card cap and whose mandatory gold gain, if available, leaves the hand at ten or fewer tokens. Its key is `2000 + canonical card ID`.

Take keys are `1000 + sum(quantity[color] * 3^color)` in white, blue, green, red, black order. Sort all actions by the numeric key. No blind reservation, excess-return branch, partial distinct take or voluntary pass appears.

The double-take hand limit preserves a seal256 native enumeration defect: `get_actions` omits a double take at eight tokens, although native `verify_action` accepts it. The measured profile uses native enumeration and reproduces that restriction in Rust. It does not replace the external enumeration with a broader verifier-based list.

Uniform random means one draw over the sorted list of main-action keys. Payment and noble subphases consume no additional policy random draw. A purchase pays each colored deficit after discounts up to the colored tokens held, then uses gold for the remaining deficit. Alternate optional-gold payments have no separate random weight. This is a policy restriction within the published payment choices.

Before applying the selected purchase, both adapters count nobles that would be eligible after its bonus gain. If two or more qualify, stop as `unsupported_noble_choice`. Do not remove that action and choose another one. The selected action has not been applied and adds no completed turn. This stop prevents seal256's first-noble shortcut from leaving a second eligible noble that the canonical engine would claim on a later take or reserve turn. Exactly one eligible noble is claimed; zero causes no noble phase.

The fixed policy buys whenever a purchase exists. It selects the lowest numeric key, so visible purchases have priority over reserved purchases. Otherwise, it selects the take with the largest `sum(quantity[color] * (8 - tokens[color]))`. Numeric key order breaks equal scores. If no purchase or take exists, it selects the lowest reservation key. It uses no policy RNG. This is the implemented common deterministic policy, not either engine's native greedy agent.

Rust executes main, canonical colored-first Payment, and any mandatory Noble phase. C++ executes its main action and then its scheduled refill chance action when needed. A chance action and a payment/noble phase are not extra player turns. Record native decisions separately, but rank common completed turns or attempted trajectories rather than unequal native-decision counts. Every native transition remains checked: Rust public apply and C++ verify_action before unchecked native apply.

## Stops and accounting

An empty projected list with canonical actions still available is `profile_blocked`. It is not a published-rule stalemate. A true canonical empty legal set is `no_legal_action`. C++ has no full published action enumerator, so its classification uses the tested no-reservation-space/empty-colored-bank condition after the shared projection is empty; cross-engine outcome checks must catch any divergent classification.

The other outcomes are `unsupported_noble_choice`, `decision_limit` at 20,000 completed player turns, and `complete` at normal end-of-round victory. No adapter forces a pass, awards a winner at a cap, or drops an unfinished case. All started cases remain in the trajectory-rate denominator. Completed games per second uses only normal completions, while elapsed time retains all attempted work.

## Measurement boundary and review limits

All case setup is serial and outside the gameplay timer. The gameplay region includes native legal generation, semantic profile projection, policy selection, checked transitions, per-game clock calls and ordered minimal record collection. Final public snapshot extraction and JSON serialization are outside it. Process wall time separately includes parsing, setup, warmup and output. Workers start before timed gameplay; dispatch, completion and collection are timed.

The current runner compares sixty-four shared cases per random/fixed policy with action keys, legal keys, state traces and outcomes before measurement. Each timing repetition uses the same larger corpus. It checks final summarized records across engines and one/multiple workers and alternates the full configuration order across repetitions. This proves equality only for the measured profile and tested cases. It does not establish complete published-action equivalence.

A pipeline speed claim must disclose all adapter work. C++ action descriptors, chance-action IDs and pointer-to-canonical-ID maps are prepared outside the timer. Per-turn checksum work has been removed; final state records consume the results in both engines. The timed C++ projection still performs pointer-map lookups where Rust already has canonical card IDs. Minimal C++ JSON record boxing versus Rust typed records is another stated limit. Call the result **aligned adapter pipeline throughput** or throughput under the declared profile; do not present its ratio as isolated application-function throughput. Preserve exact source fingerprints so the report identifies the final measured implementation.

## Python alignment feasibility

The lyquentxy Numba Board can accept an injected native array and its existing take/buy actions. Its deck stores remaining-card bitsets rather than order. `benchmarks/adapters/python_alignment_feasibility.py` solves for a native deterministic draw seed selecting the scheduled remaining-card index. Multiplier 4,594,591 is coprime with every remaining deck size one through forty. The probe verified all ninety full-deck card selections through unchanged `_get_deck_card`. No source or rule patch was needed.

This probe does not prove data, setup or full-game parity. Python still awards all eligible nobles, uses a 62-turn-per-player cap with score outcomes, and has a finite byte turn counter. An aligned Python adapter would need a verified full fixture conversion, exact same projected keys, multi-noble stops, explicit pre-cap incomplete stops, and checked projected actions. Its always-legal passes, small takes and voluntary return turns must be excluded by the declared policy. Its existing opening timings remain unchecked, unranked references. No Python whole-game ranking is enabled by this document.

## Scenario checks for extensions

Keep the normal published-rule tests authoritative. Add profile checks for hand sizes seven/eight/nine/ten; double-take bank sizes three/four; fewer than three colored piles; visible reserve with/without gold at the limit; gold-deficit colored-first payment; market/deck exhaustion and draw order; one/two eligible nobles; projected-empty versus canonical-empty states; final-round timing from each seat; exact shared ties; and incomplete caps.

For the separate optional pass API, test rejection when any canonical action exists, rejection in a pending Payment/Return/Noble phase, one pass at a true canonical no-action state, repeated passes without an invented winner, and its separate version identifier. Keep these test-only variants out of the measured intersection profile unless a new explicit profile and validation gate are added.
