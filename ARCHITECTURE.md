# Architecture

The game engine, agents, and tools have separate roles. Agents receive an
observation of the game. They do not receive the full game state.

## Workspace

| Crate | Role |
| --- | --- |
| `splendor-core` | Card data, setup, legal actions, state changes, observations, and state checks. |
| `splendor-agents` | Heuristic agents, search, and model inference interfaces. |
| `splendor-arena` | CLI, parallel games, reports, statistics, and replay. |
| `splendor-web` | Rust/WASM interface for the browser game. |

The browser interface is in `web/`. It runs rules and agent search in a worker
so that game work does not block the page.

The core uses fixed storage and explicit random state. It has no agent code,
I/O, clock, serialization framework, or ML framework. Its only production
dependency is `arrayvec`. Normal core operations do not allocate on the heap.
Search and report tools can allocate. The core, agent, and arena libraries
forbid unsafe Rust.

## Decisions and turns

A player turn can contain several decisions:

1. **Main:** take tokens, reserve a card, or select a card to buy.
2. **Payment:** choose tokens for a purchase. Gold can replace colored tokens.
3. **Return:** choose all tokens above the ten-token limit to return.
4. **Noble:** choose one noble if more than one is eligible. One eligible noble
   is taken automatically.
5. End the turn and move to the next player.

Payment and Return are separate paths in an ordinary turn. The current player
keeps control until the turn ends. Only a complete turn increases the turn
counter. The end-game check occurs after the complete turn.

The engine lists decisions separately to avoid a large combined action list.
It keeps every legal payment, token return, and noble choice. A random choice
at each decision is not a uniform choice across all complete-turn paths.

## Apply an action

`apply_action` checks an action before it changes the state. An invalid action
leaves the state unchanged.

The `Decision` API gives a caller the complete legal list for one state. It
holds an exclusive borrow of that state. It checks list membership and consumes
the decision when it applies an action. This avoids repeated rule checks and
prevents use of the list after the state changes. Direct checked application
remains available.

State copies use fixed storage. The engine has no apply/undo path. Cards and
nobles use compact IDs and bitsets. The seven-byte action wire format is
separate from the eight-byte Rust `Action` layout.

## Hidden information

An `Observation` contains the market, bank, public player data, deck sizes,
and the viewer's private reservations. An opponent's visible reservation stays
known. An opponent's blind reservation reveals only its count and tier.

An observation excludes the setup seed, random state, real deck order, and
opponents' blind card IDs. Full replay files contain private data; never give
them to an agent.

`Observation::determinize` creates a possible full state from the observation.
It assigns unknown cards without replacement within each tier and shuffles the
remaining decks. It checks the result. Each simulated player receives its own
redacted observation. The uniform sampler does not infer opponent preferences.

## Search

The CLI `search` agent uses root UCB search. It tests a limited set of actions
with heuristic rollouts and a fresh sampled hidden state per simulation. It
has no persistent search tree. `mcts` is an alias for this agent.

Research agents also support neural PUCT and Gumbel search. Their model and
search settings are part of the agent identity. Some use a separate tensor
service. See [Strategy](STRATEGY.md) for the confirmed profiles.

Strong and the classical Search agent use public checks to avoid some token
moves that would block later play when another choice exists. These checks
change agent choices. They preserve the core's complete legal action set and
do not guarantee that every game finishes.

## Determinism and replay

Setup uses SplitMix64 and a fixed shuffle order. The setup seed and action
sequence determine the game state. Cards are drawn from the prepared decks.
Each agent identity has a separate random stream. Seat rotations keep the same
setup and identity seeds. Parallel results are collected in game order.

A history stores the engine version, setup seed, and action sequence. Replay
rebuilds setup, applies each action, checks invariants, and checks the saved
state. A history can end between decisions in a turn.

The engine version is `splendorust-v2`; the history JSON format version is 1.
The replay loader rejects a different engine version. Use the matching old
source to replay v1 histories. At the turn-counter limit, a legal action returns
`TurnLimit` before mutation. This resource error gives no game outcome.

Fixed-budget records match on the tested platforms and workloads. Floating
point search is not guaranteed to make the same choices on every platform.
Recorded actions replay without the search calculation.

## Outcomes and statistics

Rank uses prestige first, then fewer purchased cards. Exact ties share rank
and split one win credit. An unfinished game has no outcome.

The arena keeps blocked and decision-limit games in its records. Canonical
comparison intervals group seat rotations by setup. Unknown outcomes give
zero credit to the lower bound and one to the upper bound. This prevents
incomplete games from inflating a result.

External benchmarks can use different rules and interval methods. See
[Validation](VALIDATION.md) for completion rules and
[Experiments](EXPERIMENTS.md) for evidence tied to each profile.
