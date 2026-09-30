# Strength profiles

Default SplendoRust rules and agent source are unchanged. The user approved the
following rule/observation adaptation on 2026-09-29. No new core rule flag is
needed for this profile. Simulator throughput results do not measure strength.

## `published-base-native-planning-v1`

Actual transitions use `published-base-v1` and engine `splendorust-v2`. Search
uses its current defaults: 128 simulations, depth eight, width six, strong
rollouts and engine evaluation. No legal-action filtering is applied to Search.
External policies use their native planners and checkpoint settings. Their
chosen main action is translated to a canonical action and checked against the
complete canonical legal set. An unrepresentable choice stops as `unsupported`.
No alternative action is selected. Pending purchases use the external native
colored-first payment. A sole eligible noble is mandatory. Multiple noble
choices or an excess-token return stop as unsupported. A normal terminal game
alone receives win credit. A 2,000-decision cap, worker timeout, invalid action,
blocked game and unsupported choice are retained separately.

## `public-observation-sampled-hidden-v1`

The Rust worker receives the setup seed only to construct the referee state.
Neither external policy receives this seed or the real deck order. A separate
sampling RNG reconstructs a world from the active player's `Observation` only.
The sampled world must reproduce that exact observation. Opponent blind
reservations are sampled, while the actor's private reservations and all
public reservations remain correct. Public purchases, token supplies, scores,
remaining deck counts and noble ownership remain exact. Each external decision
uses one such sample. This is a declared information adaptation, not the
external agent's original information model and not a full information-set
MCTS implementation. Equal observations and sampling seeds produce equal
external inputs, even when the real hidden worlds differ (Rust regression).

AlphaZero stores remaining-card identities as bitfields rather than deck order.
Its input bitfields are reconstructed from the sampled partition. All 90 card
and 10 noble tuples must match before play. Native refill/chance planning is
unchanged; actual refills use the referee's own shuffled deck. Native array
market positions map to canonical slots. Native initial noble slots stay stable.

Seal256 receives the same sampled partition. Its compact native market slots
map back to canonical market indices. Its unchanged MCTSAgent runs fresh native
MCTS at each decision. Native constructor randomness is excluded from policy RNG;
the policy uses a declared per-decision seed. All native choices pass the unchanged
native verifier before canonical translation. The only source patch changes
verifier access from private to public.

## Native planning differences

| Feature | AlphaZero | Seal256 |
|---|---|---|
| Small distinct takes | Allowed even with three colors available | Native enumeration only |
| Take and excess return | Not represented | Not represented |
| Standalone return | Full-turn action | Not represented |
| Pass | Always legal | Used when native actions are empty |
| Reserve at ten tokens | Omits gold | Grants an eleventh token |
| Optional gold payment | Colored-first only | Colored-first only |
| Noble choice | All eligible nobles on purchase | First eligible noble on purchase |
| Noble after take/reserve | Not awarded | Not awarded |
| Native cap | Score result at 62 rounds | All players skip: terminal, possibly no winner |
| Blind reservations | Supported; native input contains all identities | Not supported |

AlphaZero's external root is stopped before its native cap. Native score-based
cap results are never used as referee outcomes. Native planning can still value
these variant outcomes inside search; this remains a limitation. The native
byte counter permits up to 248 turns for four players; the root cap prevents
wraparound. Earlier inference errors are invalid games, never victories.

## `seal256-native-v1` / `seal256-native-state-v1`

This separate control uses unchanged upstream native MCTS and random policies
on the native game. The final control constructs one native setup per block and copies it for
both seat rotations. Its upstream shuffle RNG persists between blocks; exact
initial state fixtures are saved in every game record, with a separate policy seed. Chance refills use the upstream random action
list. Record native actions and native rewards. Native terminal games with
zero total reward are `native_no_winner`, with no win credit. Existing screening
raw files and original summaries are preserved byte-for-byte. Audited summaries
correct the one zero-reward game in the 500-iteration screen. Native outcomes
cannot rank SplendoRust. Pinned native reserve behavior can exceed the published
ten-token limit; this is part of the native implementation, not base-rule parity.

## Schuber6 checkpoint contract

The pinned source supplies three matrices with layer dimensions 46/30/26. The
46 inputs encode bank, player zero and four cards. The shipped move selector
uses this small game; a twelve-card encoder also exists, but no saved matching
full-game multiplayer policy is supplied. All saved weights load and infer
unchanged. Full-game integration is `unsupported`; no feature truncation,
weight resizing, opponent substitution or candidate replacement is permitted.
The stated Double-DQN/prioritized-replay/multi-step description could not be
verified in this exact repository. See `schuber6-integration.json`.

Legacy native screens and the rejected first confirmation did not actually pair
setups: upstream thread-local shuffle RNG continues despite repeated `srand`.
Their point results are historical unpaired screens. Their original intervals
remain preserved, but no validated paired interval is assigned in audited summaries.
