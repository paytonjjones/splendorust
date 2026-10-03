# Web quality evidence

The browser game uses the registered E81 champion. Its production model SHA-256 is `e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8`. Search uses Gumbel 128 simulations, depth 16, three sampled worlds, 16 root candidates, cvisit 50, cscale 0.1, and no root noise. This work makes no new playing-strength claim.

## Architecture

React renders public state from a dedicated worker. The worker loads and verifies the model, then calls `splendor-web`. The wrapper uses the existing core legal-action enumeration and the native neural agent. It accepts stable action IDs and resolves a human decision only when exactly one legal choice remains. TypeScript matches UI selections against these actions; it contains no rule engine or bot search.

The model loads from a content-addressed static file. Metadata names its hash, size, display identity, and search settings. Supported production model formats stay in the Rust inference layer. Unsupported search profiles fail with an explicit error. A new supported neural architecture needs no board changes. The client interface can later accept a remote implementation.

The board receives the human observation. Bot blind reservation identities, deck order, and setup seed are absent from UI snapshots. A separate private training journal contains the setup seed and exact diagnostic state for offline replay validation. Agents still receive only their Observation. A normal build excludes the test bridge, including with `?test=1`. The test build calls the same worker and action methods.

## Champion profile integration hypothesis

**Hypothesis:** WebGame must create its externally loaded model agent through the canonical `flywheel-gumbel` factory profile. The factory sets the champion's exploration constants (`cpuct=0.4`, `fpu_reduction=0.02965`, `uniform_prior=0`) when it configures a non-empty world pool. The earlier WebGame setup copied the champion's visible JSON settings but left those three values at generic neural defaults. A parity test that duplicated wrapper setup could therefore pass while the web bot still differed from the registered champion.

**Check:** Inject the same registered E81 model into the canonical factory for the native comparison. Compare its opening choice to WebGame at 128 simulations, depth 16, and the registered search profile. WebGame passes champion metadata values as typed profile overrides after factory initialization, so supported settings remain replaceable without changing Rust source. This is an integration correctness check, not a search-strength change.

## Design review

Three distinct directions were rendered in real browsers at desktop, laptop, and mobile sizes: Atelier (ivory paper and architectural engravings), Midnight Guild (dark mineral table and brighter gems), and Modern Ledger (a compact, neutral graphic board). The studies are saved as `study-*.png`. The user selected Atelier and asked for darker cards.

The lead reviewed layout, card proportions, cost legibility, token identity, and player separation. Refinements retained a light table, added darker mineral card colors, replaced all vector illustrations with generated raster atlases, reduced decorative density, made mobile reserve controls visible, tightened the laptop board, and improved low-contrast text. Repeated screenshots are saved as `atelier-first-*`, `atelier-second-*`, and final `screenshots/*`. Roman deck labels use a smaller sans serif face so they fit narrow stacks. The follow-up [design review](DESIGN.md) uses online research to remove repeated framing, decorative labels, weak visual hierarchy, and vague copy. It retains the original art and game information. The lead inspected fresh desktop, laptop, and mobile screenshots, including the 320-pixel layout and the midgame board.

Cards, gems, reservations, and nobles move between their board positions. Market replacement and score changes use short transitions. Reset cancels pending motion and terminates the old worker. Reduced-motion settings skip spatial animation. The normal UI adds no fixed bot thinking delay.

The three generated atlases total 142,466 bytes. The same six architectural motifs serve all cards; six gem designs and three patron seals complete the asset set. Asset prompts and provenance are in [ASSETS.md](ASSETS.md). No SVG illustration or third-party game artwork is used.

The asset alignment correction centers the visible illustration bounds rather than each atlas cell. It preserves the source proportions and fits complete buildings between the header and cost strip. Mobile cards leave room for Reserve. The lead inspected fresh screenshots at 1728, 1365, 390, and 320 pixels, including a reserved card and the card-details dialog. A browser check mapped source alpha pixels through the actual CSS scale and position for opening, reserved, and card-details states at all four sizes. All 12 checks found centered assets and no overlap with card headers, costs, or visible Reserve controls. Measurements are in [asset-alignment.json](asset-alignment.json). The seven focused accessibility, keyboard, mouse, and viewport tests pass, including a complete arrow-and-Enter game whose downloaded log passed native replay validation.

## Manual play

After the champion profile correction, the lead played two complete games through the normal production UI, without the test bridge. The bot won 15–12 and 15–1. These games checked single and double gem takes, affordable card purchases, visible reserves, purchases from reserves, forced gold substitution, free purchases, two human patron awards, opponent moves, equal-turn completion, result presentation, and Play again. Two earlier manual games checked voluntary gold substitution and excess-token returns, but used the incorrect search defaults and are not counted as champion games. A development game interrupted by hot reload is also not counted.

One interaction check used the payment selector's exact label, which also contained its option text. Selecting the control by its accessible combobox role worked. No game-state correction was needed. Small copy defects found during manual play were fixed: singular gem returns, final-board instructions, and movement text during human animation.

## Automated checks

Native and browser search agree for the seed 91337 opening at the actual champion budget: the bot chooses `take:0,0,0,2,0`. The native comparison uses the canonical agent factory with the registered model and no web profile overrides. Native tests cover reachable multi-noble selection, legal choices, hidden reservations, invalid actions without state mutation, and complete games.

Formatting, strict release workspace Clippy (default and all features), WASM-target Clippy, and locked release workspace tests pass: 133 tests with default features and 139 with all features. TypeScript and production builds pass. Browser results and per-game status records are in [playtest.json](playtest.json). The 30 seeded full games use the actual production model and search settings. Their outcomes test product completion; they are not an arena strength estimate.

All 20 browser tests pass. The 30 full games finished with zero blocked games and zero errors. The suite checks WCAG A/AA with Axe, four viewport widths (1728, 1365, 390, and 320), horizontal overflow, console errors, keyboard gem takes and purchases, reserve controls, dialog close and focus restoration, refresh, and reset during an active worker request. Arrow-and-Enter tests play a complete game, select payment alternatives, return excess tokens, and choose among nobles through visible controls. The browser JSONL download replays through the native Rust validator. Recorder checks cover exact u64 seeds, rejected actions, refresh recovery, failed uploads, delayed acknowledgments, copied tab storage, unavailable IndexedDB, and immediate control disabling before a delayed worker receives an action. All 24 backend checks pass, including concurrent writes, immutable replay prefixes, sealed outcomes, private exports, and request limits.

The rare multiple-noble UI check replays the current Rust seed-10 action sequence with 2 simulations and depth 3. It keeps the E81 model, canonical factory, and Gumbel parameters. It reaches exactly two legal choices, `noble:8` and `noble:9`, and selects a visible tile. The reduced budget is enabled only in development/test builds. Full games, champion parity, and performance checks use the registered 128-simulation, depth-16 profile.

The mobile viewport performance check played 20 bot turns with Chromium CPU throttled by a factor of four. Bot-turn latency was 91.3 ms at p50, 93.6 ms at p95, and 95.5 ms maximum. During search, animation frame intervals were 16.67 ms at p50, p95, and maximum, with no gaps above 50 ms. Raw samples, initialization and model-load timings, and the champion profile are in [performance.json](performance.json).

Performance numbers are local Chromium measurements on this host. CPU throttling approximates a slower device; it is not a physical-phone benchmark or an Internet download measurement. Static assets use immutable cache headers. Each visitor runs search in their own worker, so concurrent games do not share a server inference queue.

## Public deployment

The production game is live at [splendorust.pages.dev](https://splendorust.pages.dev). Public checks confirmed successful HTML and model requests, the E81 model hash and byte count, no-cache champion metadata, immutable model/WASM assets, `application/wasm` MIME, and the content security policy. The normal public UI completed a game at 15–5 with no browser errors. Uploads succeeded, the browser JSONL download worked, and GET on the journal endpoint returned 405. The production page exposes no test bridge. See [public-check.json](public-check.json).

The private D1 export contained four launch-check games: three finished and one interrupted in progress. All four replayed through the native Rust validator with zero rejections. The completed public game's central record exactly matched its browser download. Exports contain no write tokens. The retained count and record-set hash are in [recording-check.json](recording-check.json); raw private data stays in ignored `local/web-games/`. The site records all visitor games, with a durable browser queue and retry. See [GAME_LOGS.md](GAME_LOGS.md) for export, request limits, and pending-record loss conditions.

The screenshot is saved as `screenshots/public-bot-reply-1365x768.png`. GitHub Actions remains disabled in the repository settings.
