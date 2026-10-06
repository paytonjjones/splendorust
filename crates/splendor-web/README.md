# SplendoRust browser API

The `splendor-web` crate wraps the canonical Rust engine and the observation-only
neural search agent. It does not implement rules in Rust bindings or in the web
client. It builds as `cdylib` and `rlib`; wasm-bindgen emits
`splendor_web.js` and `splendor_web_bg.wasm`.

The `external-model-only` feature removes arena research checkpoints from the
browser binary. The web build must enable this feature. Workspace builds leave
it off so native research agents retain their embedded models and behavior.
Decoded model bytes are cached by exact asset bytes for the worker lifetime.
The UI starts a new worker on restart to cancel active search. Static model bytes
remain in the browser cache, and the new worker decodes them again.

The integration hypothesis is that the current champion can run in a browser
when its supported `.bin` model and search profile are supplied as static
assets. This change makes no strength claim and does not change rules or the
default search behavior. The wrapper supplies the E81 profile defaults:
128 simulations, depth 16, three sampled worlds, Gumbel max considered 16,
`cvisit` 50, `cscale` 0.1, and root noise 0. Search settings can be replaced in
the JSON configuration without a Rust code change.

## API

`new(seed, humanSeat, modelBytes, configJson)` creates a two-player game.
`seed` accepts unsigned decimal or `0x` hexadecimal text. The setup seed is
never returned. `humanSeat` is 0 or 1. `modelBytes` contains a production model
supported by the inference crate. `configJson` accepts camel-case fields
`iterations`, `depth`, `worldPool`, `gumbelMaxConsidered`, `gumbelCvisit`,
`gumbelCscale`, and `gumbelRootNoise`; omitted fields use champion defaults.
`searchAgent` accepts `flywheel-gumbel` or `flywheel-best`. The latter accepts
`cpuct`, `fpuReduction`, `dynamicFpu`, `chanceUniverses`, `uniformPrior`,
`rootOnly`, and zero `rootNoise`. `gpuInference: true` uses the host Entity
backend. The callback receives only tokens from the public observation.
The web application supplies the current champion settings. It sets an
absolute monotonic deadline with `botStepWithDeadline(deadlineMs)` for each
bot decision. All decisions in a turn share one deadline. Ordinary
`botStep()` calls keep the fixed simulation budget.

`snapshot()` returns JSON with `revision`, `turn`, `activePlayer`, `humanSeat`,
`stage`, `finalRound`, `bank`, `market`, `deckCounts`, `nobles`, `players`,
`pendingCard`, `legalActions`, `result`, and `lastEvents`. A card contains its
stable engine id, one-based tier, bonus color, prestige points, and five-color
cost. A player contains tokens, bonuses, score, owned cards, and three
reservation slots. A blind opponent reservation retains its public tier and
hidden flag; it never contains its card id or cost. Legal actions are returned
only for the human seat.

Action IDs are deterministic and encode the exact engine choice: `take:<five
counts>`, `reserve-visible:<slot>`, `reserve-deck:<zero-based tier>`,
`buy-visible:<slot>`, `buy-reserved:<reservation index>`, `pay:<five counts>`,
`return:<six counts>`, and `noble:<id>`. The legal list preserves every payment,
token return, and noble choice. `act(actionId)` applies one human action and
automatically applies subsequent forced human decisions only while one legal
choice exists. `bot_step()` applies one bot engine decision. `play_bot_turn()`
applies the bot's decisions until the human turn begins or the game finishes.

`lastEvents` contains only actions from the most recent mutating API call. Each
event has its revision, actor, action id, kind, and relevant take, payment,
gold payment, return, slot, tier, card id, or noble id. A human's private deck reservation
card id is visible to that human. A bot's blind reservation remains redacted.

Results have `status: "finished"` and the engine winner mask/ranks/scores, or
`status: "blocked"` with winner mask and ranks set to zero and a reason of
`no_legal_action` or `decision_limit`. A blocked game is not reported as a
loss or win.
