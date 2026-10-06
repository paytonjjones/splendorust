# Browser champion check

The browser uses the registered Entity weights, dynamic FPU, and PUCT6400.
The chance-universe setting is passed through, but fixed chance universes
apply only to the native research environment. Canonical browser rules keep
their existing refill behavior.
The native Rust reference, with canonical rules, and WASM worker chose `take:0,0,0,2,0` after the human
played `take:1,1,1,0,0`, with seed 91337. Both ran 6,400 simulations.

The WASM decision took 415.45 seconds (6.9 minutes) in headless Chromium,
on this Apple M4 Pro, with a 390 × 844 viewport and no CPU throttle.
A 20 ms page timer ran 20,772 times during the move. Its largest gap was
21.78 ms. These values describe one opening decision, not all game states
or mobile hardware. The native reference pair took 674.27 seconds.

The portable CPU runtime is much slower than E81. The confirmed research
run used a batched model service and native rules. This check verifies the
weights, configuration, search budget, replay, and one matched decision.
It does not establish a browser win rate.

See `native.json`, `browser.json`, `build.json`, and `checks.json` for evidence.
The full native test is opt-in because it takes several minutes. The normal
release workspace tests, strict Clippy, format check, web type check, game-log
checks, and both web builds passed. GitHub Actions stays disabled.

## Public deployment

Cloudflare production deployment `a1cba1e1-92e0-4907-a96e-9150f897f7ec`
uses source commit `5fe6aa2`. Public model bytes and SHA-256, HTML, worker,
and WASM match the tested production build. The live page exposes no test
bridge. A normal UI move ran exactly 6,400 simulations in 417.79 seconds
(7.0 minutes). The page timer's largest gap was 30.5 ms. Both game-log
uploads returned HTTP 202. See `deployment.json` and `live.json`.

Reload the page to load this runtime. A reload starts a new game. An already
loaded E81 game can finish with its original runtime; the new log endpoint
continues to accept its legacy search fields.
