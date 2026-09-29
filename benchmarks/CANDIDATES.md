# Benchmark candidate inventory

Source and local manifests checked on 2026-09-29. This inventory records installation,
API and rule status. It does not rank speed. Read [PROTOCOL.md](PROTOCOL.md) for timing
boundaries and [PROFILES.md](PROFILES.md) for the exact shared action space.

A public repository without a code license is a reference candidate. Do not assume
that public access grants an open-source license. External source stays in ignored,
isolated directories. Only our adapters, manifests, interface patches and functional
data checks are retained in this repository.

| Candidate | Pinned revision | Runtime | License found | Installation and comparison status |
|---|---|---|---|---|
| [seal256/splendor](https://github.com/seal256/splendor) | `263abc066c563a1c89dba4bdc408446a20ad9d1d` | C++ | No license file found | Optimized engine and adapters built. Viable for the checked opening transition and the explicit aligned game profile. |
| [lyquentxy/splendor](https://github.com/lyquentxy/splendor) | `32a27ac1f85d5de2766cc5f60c2bf04e557f7836` | Python/Numba | MIT | Isolated runtime verified. Opening adapter is unchecked and unranked. Whole-game alignment remains a feasibility probe. |
| [roeey777/Splendor-AI](https://github.com/roeey777/Splendor-AI) | `95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b` | Python | MIT | Engine and aligned prefix adapter verified. Unranked because of the seven-bonus cap and mandatory history bookkeeping. |
| [inclement/lapidary-ai](https://github.com/inclement/lapidary-ai) | `4680663785da947fb77d99f9ab77326f24087633` | Python/NumPy | No top-level license found | Seeded setup and native legal generation verified. Retained as a non-comparable reference. |
| [bouk/splendimax](https://github.com/bouk/splendimax) | `5ffcb148ee0093e3b47f612b04a1927301ff13ee` | Rust | No license file found | Release build verified. Rule differences and an upstream test failure exclude current rankings. |
| [AverageStardust/splendor-engine](https://github.com/AverageStardust/splendor-engine) | `3a85b8c8c6f050b1dcebb53820f7cf0861fcba5e` | Go | No license file found | Main binary and rule probe built. Runtime probe confirms invalid take generation. Excluded from current rankings. |
| [cestpasphoto/alpha-zero-general](https://github.com/cestpasphoto/alpha-zero-general) | `846b919f781b871da2fff0a05fb4ae069d1a9d45` | Python/Numba | MIT | Original source cloned and inspected. No runtime result claimed. Optimized fork is listed separately above. |

## seal256: viable shared workloads

The engine supports two, three and four players. Its public state exposes bank,
players, market, decks and nobles. Available APIs include `get_actions`, `clone`,
`apply_action`, `is_terminal` and rewards. Native `apply_action` disables validation.
Our patch exposes the existing private `verify_action` method through public access;
it changes no rule or function body. Both checked adapters call it before applying.

The normal engine omits blind reservations, overflow-return choices and partial
bank-exhaustion takes. It uses colored-first payment and automatically grants the
first eligible noble on purchases. Its native enumeration also omits a double take
at exactly eight held tokens. Native empty-action states become passes, and an
all-pass round can end a game. Normal score termination occurs at the equal-turn
round boundary; fewest purchased cards and shared victories are supported.

The opening adapter compares only clone plus checked white/blue/green take from a
two-player opening. Other rule choices are absent from that operation. The aligned
`seal256-intersection-v1` adapter uses shared ordered decks, mapped functional card
and noble IDs, sorted semantic action keys, shared SplitMix64 selection and an exact
common fixed policy. It excludes overflow and blind actions, preserves the native
double-take restriction, never selects pass, and stops before a selected purchase
could qualify for multiple nobles. Incomplete outcomes remain in the result file.

This is viable **aligned adapter pipeline throughput**. It is not unrestricted
base-game equivalence or an isolated function-cost ratio. Native chance transitions
and Rust payment/noble phases differ; common player turns are the comparison unit.
The native MCTS iteration and neural-policy interfaces exist, but no cross-engine
search ranking is enabled by these adapters.

Setup uses native thread-local MT19937 seeded from `std::rand`. The opening adapter
sets its startup seed. The aligned game adapter injects common setup and consumes no
native setup randomness during timed play. Action descriptors, card-pointer maps
and chance-action IDs are cached before timing. See
[NATIVE_AUDIT.md](external/NATIVE_AUDIT.md),
[native-candidates.json](external/native-candidates.json),
[setup_native.py](external/setup_native.py) and
[seal256-interface.patch](external/seal256-interface.patch).

## lyquentxy: unchecked opening reference

The public `SplendorGame` wrapper defaults to two players. Its internal Numba Board
supports two through four. The installed environment uses Python 3.12.7,
NumPy 1.26.4, Numba 0.62.0 and llvmlite 0.45.1. NumPy 2.3.3 failed because upstream
uses `np.bool8`; dependency pinning resolved this without a source patch.

The API provides initial state, valid actions, next state and termination queries.
Its opening adapter checks expected input/output array changes, but the timed native
transition does not validate action legality. It therefore remains in the separate
unchecked-reference group. Do not give it a ratio against checked Rust or C++ apply.

Rule differences include always-legal pass, smaller distinct takes when more colors
remain, separate voluntary-return turns, no taking above ten, reservation at ten
without mandatory gold and a return, colored-first payment, all eligible nobles
awarded on purchase, and score-based outcomes at the 62-turn-per-player cap. The
native deterministic draw helper can select scheduled cards through an adapter
seed, but that probe alone does not establish complete setup or game parity.
No training or inference framework was installed for this engine benchmark.
See [python_lyquentxy.json](external/python_lyquentxy.json) and the Python alignment
section in [PROFILES.md](PROFILES.md).

## Roeey: aligned prefixes, no speed ranking

The engine supports two through four players; the adapter supports two. Its unchanged
rule interface supplies native legal actions and compound successors. The adapter
injects common deck/noble order once, checks selected compound-action membership,
and applies the native rule update. It verifies the complete 90-card and 10-noble
functional multiset before use. No upstream source is patched and only the Python
standard library is required for this engine path.

Native legal enumeration omits an otherwise affordable purchase when the player has
exactly seven bonuses of that color. The adapter keeps the common semantic key and
stops as `unsupported_reference_bonus_cap` if that choice is selected. It does not
remove the choice, change its random weight or patch the cap.

Native successors also append mandatory in-memory `action_reward` history. Legal
search deep-copies this history. There is no logging-disable API. This cost remains
enabled and violates the suite's logging-excluded comparison contract. Thus, even a
matched prefix cannot enter the ranking. Two 12-turn prefixes, one random and one
fixed, matched states, projected legal keys, selected keys and final state. This is
24 matched turns, not complete-game or speed evidence. Full-rule noble, return,
blind-reservation, pass and multiplayer differences remain in the parity audit.
See [python_roeey.json](external/python_roeey.json) and
[PARITY.md](../docs/PARITY.md).

## Lapidary: engine verified, different information and rules

`GameState(players, init_game, validate, generator)` accepts a NumPy RandomState.
Engine methods include `get_current_player_valid_moves`, `copy` and `make_move`.
Two-to-four-player engine setup is supported; the trained AI is for two players.
A Python 3.12.7/NumPy 1.26.4 smoke imported the engine, created a seeded two-player
setup and generated 30 opening actions without TensorFlow.

Its declared changes expose blind reservations and actual deck order to the AI.
It permits fewer than three distinct tokens, automatically takes the first noble,
uses gold only for color deficits and converts no-move states to printed passes.
These differences exclude complete-game and search rankings. Neural runtime was not
installed. See [python_lapidary.json](external/python_lapidary.json).

## Splendimax: release build, incomplete transition model

This two-player Rust engine exposes `generate_moves`, `apply`, `undo` and
`is_terminal` through its algorithm state trait. It has no native clone API.
Setup uses `rand::thread_rng`, with no public setup-seed interface. Minimax and
alpha-beta search are available.

The release build succeeds. The source-only isolation patch appends an empty Cargo
workspace table; it changes no gameplay. A resolved lock file is retained. Nine
library tests pass, while `generate_possible_moves` deliberately asserts false.
Blind reservations are missing, payment choices collapse, returns omit newly taken
colors and gold, and reserved-token returns fail to restore the bank. Market refills
occur outside `State::apply`. The engine permits forced pass and terminates
immediately at 15 points instead of finishing the round. Its search thus uses a
different transition model. See [native-candidates.json](external/native-candidates.json),
[splendimax-isolation.patch](external/splendimax-isolation.patch) and
[splendimax.Cargo.lock](external/splendimax.Cargo.lock).

## AverageStardust: concrete invalid-action evidence

The Go engine supports two through four players through `NewRandomGame`, `NewGame`,
`Game.Moves` and `Move.Apply`. It uses the global `math/rand/v2` state without a seed
injection API. The README describes MCTS, but pinned agent source implements MaxN
and a threaded MaxN depth search.

The official Go 1.27.1 macOS ARM64 archive was installed in the isolated directory
and verified against its published SHA256. The main binary builds.
`go test ./...` compiles all packages, but there are no test files. No source patch
is applied.

Triple-take generation ignores bank availability and emits six permutations per
color set. The executable probe produces 60 take actions when every bank pile is
empty; transfer clamps unavailable tokens rather than rejecting the requested move.
Reserved-card purchases and blind reservations are absent. Gold availability on
reservation, the greater-than-15 victory threshold and tie handling also differ.
This source and runtime evidence excludes current rankings. See
[averagestardust-rule-probe.json](external/averagestardust-rule-probe.json) and
[NATIVE_AUDIT.md](external/NATIVE_AUDIT.md).

## Original AlphaZero and discovery-only references

The original cestpasphoto Numba Board supports two through four players, while its
wrapper defaults to two. APIs include `getInitBoard`, `getNextState`, `getValidMoves`
and `getGameEnded`. It uses NumPy randomness for setup and a custom deterministic
remaining-card mapping when a nonzero draw seed is supplied. It awards all eligible
nobles and produces points-based winners at a 62-turn-per-player cap. This pinned
source was inspected; no runtime or speed result is claimed for it.

[Rinascimento](https://arxiv.org/abs/1904.01883) is a published Splendor planning
framework. It is a useful next candidate for a Java planning baseline. This session
has not pinned its code, verified its license, installed its runtime or measured it.
It remains a discovery-only reference. Further public Python ISMCTS projects were
found during search, but no install or comparable-result claim is made for them.

## Remaining comparison work

The current viable cross-engine whole-game group contains Splendorust and the C++
engine under the explicit intersection profile. The Python opening helper is
unchecked; Roeey has a known action cap and required logging cost. The other
installed engines have concrete rule or information mismatches. A stronger claim
needs another independently checked implementation, a larger common trace gate,
and explicit profiles for every additional rule variant. Search comparisons need
matching rules, observations and declared fixed compute budgets before timing.
