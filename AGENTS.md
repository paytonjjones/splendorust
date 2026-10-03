# Project instructions

This is a Rust simulator/research project. Read README.md, VALIDATION.md, and EXPERIMENTS.md before changing rules or agents.

- Use the pinned toolchain and Cargo.lock. Run cargo fmt, strict workspace Clippy, and release workspace tests for Rust changes.
- Keep the core independent of agents, I/O, clocks, and serialization. Do not allocate in normal core transitions.
- Agents receive Observation only. Never expose the setup seed, real deck order, or an opponent's blind reservations.
- Preserve all payment choices, token-return choices, and mandatory noble choices. Use targeted rule tests for any change.
- Bump ENGINE_VERSION if card IDs, RNG behavior, enumeration, rules, or replay semantics change. Keep golden replay fixtures versioned.
- Do not invent victories for blocked or capped games. Report the published-rule gap. Use the registered conservative completion policy in scripts/promote.py: retain all unknown outcomes, allow at most 1% no-action games by default, and reject decision-limit games. Strict completion uses --max-no-action-fraction 0.
- Before an agent change, write a hypothesis. Record failed experiments as well as successful ones. Use fresh confirmation seeds and fixed budgets.
- Use scripts/promote.py for a reproducible promotion decision. A statistical result is conditional on its stated opponents and compute budget.
- Run benchmarks in release mode. Compare the same seeds and build settings. Use the source fingerprint and record-set hashes to identify an experiment.
- Keep visual assets, runtime LLM calls, GUI work, and heavyweight ML frameworks out of this project.

- Inner learning loop: use about 2,000 paired games; reserve 20,000 confirmations for milestones, external claims, or ambiguous results. Measure arena/self-play scaling above four threads.

- GitHub Actions is disabled at the user's request. Keep it disabled during research work. Run required checks locally.
