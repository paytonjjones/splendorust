# Native candidate audit

Inspected 2026-09-28. Candidate commits and rule decisions are in `native-candidates.json`.
External source stays below ignored `local/benchmarks/external`. The repository contains only
our interface code, source-access patches, installation script, and audit results.

## C++: seal256/splendor

The optimized engine builds without PyTorch by compiling only `splendor.cpp` and
`game_state.cpp`. The adapter uses the native heap-allocated `clone()` API. It then
calls the native validator and applies one opening take. The patch only makes the
existing validator public. It changes no function body or rule. Keep this patch
visible in any result description.

Run `python3 benchmarks/external/setup_native.py seal256`, then run
`local/benchmarks/external/seal256-opening --iterations 1000000 --threads 1 --seed 12345`.
A four-thread run uses the same initial state, with no RNG in the timed operation.
Thread construction, engine setup, and 1000 warm-up operations per worker occur before
the timer. Thread release and join, native clone allocation, validation, application,
checksum, and clone destruction occur inside it. Console JSON output occurs afterward.
The setup script reports build cost separately. The adapter reports setup/warm-up time.

The smoke checks starting bank, player count, zero tokens/bonuses/score/reservations,
active player, round, noble count, and winning threshold. It checks that the selected
action is legal. After application it checks bank and player tokens, next player,
round, no pending chance event, and unchanged decks/market/nobles. The timed workload
has no purchase, payment, return, noble selection, or refill. Those rules therefore
do not affect this restricted comparison. This does not establish full-game parity.
The setup seed does not imply matching deck order across implementations.

The native engine omits several base-game choices and permits forced pass. Unrestricted full games
and full legal-action enumeration must stay outside comparable rankings. The engine's
C++ MCTS and policy interfaces are useful future references for variant-specific search
cost. They do not currently support an equal-rules search comparison.

## Rust: bouk/splendimax

`python3 benchmarks/external/setup_native.py splendimax` verifies a release build.
The only source patch appends an empty `[workspace]` table, so Cargo does not treat
this isolated clone as a member of Splendorust. The resolved lock file is retained in `splendimax.Cargo.lock` and copied into
the isolated clone. Builds use `--locked`. The unmodified library test suite has 9 passes and 1 failure. The
failure is an intentional `assert!(false)` in `generate_possible_moves`.

Source inspection finds missing blind reservations, incomplete token-return choices,
colored-first payment, reserve-return token loss, forced pass, and immediate victory.
`State::apply` advances the player. Market refills occur only in the playing binary,
so search transitions use a different world model. Do not present this engine as a
full-game or search speed comparison. There is no native clone API. A custom state
copy would require its own measurement boundary and is not added here.

## Python/Numba: cestpasphoto/alpha-zero-general

Pinned original source is cloned as `cestpasphoto`. The MIT license is present.
The Board supports 2–4 players; the wrapper default is two. Source gives all eligible
nobles on a purchase and uses a move cap that creates a points-based winner. Setup
uses Numba NumPy RNG, while nonzero next-state seeds use a custom deterministic card
mapping. No runtime claim is made for this original clone. The optimized fork is
handled by the separate Python adapter audit.

## Go: AverageStardust/splendor-engine

Pinned source builds a 2–4 player game with functional replacement-style transitions.
The README describes MCTS, but the pinned agent source implements MaxN depth search.
Triple-take generation ignores bank availability and emits six permutations for each
set. Reserve always transfers a gold token, purchases of reserved cards are missing,
blind reservations are missing, and victory requires more than 15 points. These
source defects exclude full games before timing. The official Go 1.27.1 macOS ARM64 archive was installed in the isolated
directory and checked against SHA256
`ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12`.
`go test ./...` passes compilation; all packages report no test files. The main
binary builds. No external source is patched. `external_go_probe.go` demonstrates
60 emitted triple-take actions when the complete bank is empty. Their transfer
clamps unavailable tokens rather than rejecting the requested move.
Reproduce with `python3 benchmarks/external/setup_native.py averagestardust`,
then `local/benchmarks/external/averagestardust-rule-probe`. This probe is not
a game-throughput result.

## Other references found

[Rinascimento](https://arxiv.org/abs/1904.01883) is a published Splendor planning
framework. Its 2021 follow-up explores behavior space and rule variations. It is a
high-value future baseline, but this audit does not claim installation, license
verification, or speed data for it. A Go MCTS repository, optimized Numba AlphaZero,
and the old Rust alpha-beta engine give broader coverage than a Python-only survey.

## Aligned whole-game profile

The later `external_seal256_game.cpp` adapter supports the explicit
`seal256-intersection-v1` benchmark profile. This is a subset of base-game choices.
It preserves the native legal-action enumeration, including its double-take
omission at exactly eight held tokens. It removes blind reservations and token
overflow actions. A colored-first payment policy removes payment-choice differences.
A game stops before a selected purchase can qualify for two or more nobles. This
stop is `unsupported_noble_choice`, not a win. Empty projected sets are
`profile_blocked`, or `no_legal_action` when the complete base-game action set is empty.
The adapter never selects native pass.

The common corpus stores core card and noble IDs and explicit draw-order decks.
All 90 card tuples and 10 noble tuples matched the external functional data.
The corpus contains explicit core-to-native ID mappings; IDs are not assumed equal.
The native market compacts after removal; policy keys use card identity and snapshot
markets are sorted. Deck draws use the next common draw-order card through the native
chance action. Core default rules and RNG are unchanged.

Both policies use sorted common action keys. Random selection uses the exact
SplitMix64 rejection sampler from Splendorust. Fixed selection buys first; otherwise
it maximizes token quantities times `(8 - held tokens)`, with smallest-key ties, then
falls back to a visible reservation. Per-turn normalized snapshots, selected keys,
and projected legal keys are available with `--trace`. Trace runs are validation
only. Initial snapshot plus every completed turn is retained.

An initial 64-case validation matched every selected key and normalized per-turn
state for random and fixed play. Random: 44 completed, 16 profile-blocked, 4
unsupported noble choices, 3588 turns. Fixed: 51 completed, 4 profile-blocked,
9 unsupported noble choices, 3719 turns. Later legal-key validation strengthens
this evidence. These figures do not establish unrestricted-game equivalence.

`setup_native.py seal256` builds both the opening and game adapters. Game adapter
arguments are `--corpus PATH --policy random|fixed --threads N --repetitions N`,
with optional `--trace` and `--max-turns N` (default 20000). Every fixture state is
prepared before timing. Setup and worker startup costs are separate. The measured
batch includes profile generation, policy selection, native validation, transitions,
per-game clocks, and minimal result collection. Final snapshots and JSON serialization
are outside the batch timer. Native chance transitions and core payment/noble phases
have different counts; comparable throughput uses completed player turns.

A methodology review removed avoidable adapter costs before final timing: cached
native action descriptors replace per-action string parsing, card-pointer mappings
and chance-action indices are prepared before timing, and the unequal per-turn
checksum loop was removed. Native ACTIONS has internal linkage, so descriptors are
parsed once during startup rather than exposed with another external source patch.
One complete untimed warm-up game runs per process. The adapter still projects and
sorts native actions into common identity keys; that policy-interface cost is
explicit and necessary for the matched workload.
