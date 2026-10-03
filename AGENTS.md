# Project instructions

This is a Rust simulator/research project. Start with STRATEGY.md and
research/sprint48/README.md for the current strength campaign. Then read
README.md, VALIDATION.md, and the relevant entries in EXPERIMENTS.md.
The user approved this new campaign on 2026-10-03. It supersedes old research
schedules, cost vetoes, fixed sample counts, and the closed study's next steps.

- Use the pinned toolchain and Cargo.lock. Run cargo fmt, strict workspace Clippy, and release workspace tests for Rust changes.
- Keep the core independent of agents, I/O, clocks, and serialization. Do not allocate in normal core transitions.
- Agents receive Observation only. Never expose the setup seed, real deck order, or an opponent's blind reservations.
- Preserve all payment choices, token-return choices, and mandatory noble choices. Use targeted rule tests for any change.
- Bump ENGINE_VERSION if card IDs, RNG behavior, enumeration, rules, or replay semantics change. Keep golden replay fixtures versioned.
- Do not invent victories for blocked or capped games. Report the published-rule gap. Use the registered conservative completion policy in scripts/promote.py: retain all unknown outcomes, allow at most 1% no-action games by default, and reject decision-limit games. Strict completion uses --max-no-action-fraction 0.
- Before an agent change, write a short hypothesis and a finite resource budget. Record failed and uncertain experiments. Use fresh final seeds and freeze the candidate before final evaluation.
- Use scripts/promote.py for canonical promotion decisions. Use the native benchmark and its record-derived statistics for the pinned AlphaZero target. A result is conditional on its opponent, rules, information, and compute budget.
- Run benchmarks in release mode. Compare the same seeds and build settings. Use the source fingerprint and record-set hashes to identify an experiment.
- Keep splendor-core independent of ML frameworks. PyTorch/MPS and other local training or inference backends are allowed in isolated research code. Model size, latency, search depth, simulations, and unequal compute have no fixed strength limit. Keep runtime LLM calls out of game decisions. The existing web demo is outside this campaign's work scope.

- Use small, fixed exploratory screens to select research branches. Neither 2,000 development games nor 20,000 confirmation games is mandatory. Select one fresh final sample size before its outcomes, within the deadline. Keep all seat rotations and unknown outcomes. Do not stop a fixed-sample test when its interval first looks favorable.
- Use research/STRENGTH_CHAMPION.json as the confirmed research baseline. research/CHAMPION.json is the current standalone/demo runtime pointer; research/EFFICIENCY_CHAMPION.json states its measured cost scope. Do not make new strength candidates clear an equal-latency gate or repeat Entity's completed confirmation.
- One Sol agent owns decisions and integration. It may task up to five Luna helpers, within the actual tool slots. Helpers may read, audit, or implement bounded tasks. One owner schedules heavy Mac jobs; five helpers do not authorize five concurrent GPU jobs.

- GitHub Actions is disabled at the user's request. Keep it disabled during research work. Run required checks locally.
