# Browser champion check

The local browser uses the registered Entity weights and PUCT6400 settings.
The native reference and WASM worker chose `take:0,0,0,2,0` after the human
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
