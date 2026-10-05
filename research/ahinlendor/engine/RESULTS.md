# Raw engine measurements

This run compares low-level Rust and AhinLendor C++ operations on four matched
synthetic sampled worlds: start, midgame, later game, and one buy-refill state.
It measures no model, MCTS, full turn, or playing strength. The sample worlds
come from public observations and independent determinization. Their hidden
decks and hidden reservations exist only in the benchmark fixtures; they are
not agent inputs.

The C++ runner accepted all four Rust material digests. It also matched the
three tier-top reserve draws, the visible-buy refill card, the supplied TAKE
legality, and the full post-TAKE material and phase digests. Rust and C++ had
the same legal-action counts and TAKE counts on these four fixtures: start
30/15, refill 18/2, mid 26/11, and late 25/10. These counts do not prove that
the full action sets are equal. AhinLendor buys atomically; Rust enters a
payment phase. Token-return and other choices also differ.

The table shows operations per second. For each fixture, I took the median of
three repeats. The table then gives the median and range of those four
per-fixture medians. It describes this host and this build only.

| Operation | Rust median (range) | C++ median (range) | Scope |
| --- | ---: | ---: | --- |
| Apply supplied TAKE | 104.0M (102.0–111.4M) | 118.9M (116.1–119.4M) | Closest direct comparison. Both apply the same legal TAKE to matched material. |
| Generate legal actions | 14.1M (13.4–14.8M) | 3.7M (3.4–4.5M) | Output is consumed with a compiler barrier. Action representations and legal-action semantics differ. |
| Clone, then apply TAKE | 44.9M (44.2–45.6M) | 7.9M (6.4–9.5M) | State layouts and copy costs differ; this is not a search-speed ratio. |
| Enumerate actions, then apply TAKE | 13.2M (12.8–13.7M) | 2.4M (2.3–2.9M) | Tree-like primitive only. The legal-action spaces differ. |

I do not compare clone alone. Rust copies a fixed-size state, while the C++
state owns dynamic vectors. The terminal checks also do different work: Rust
checks its stored phase, while C++ evaluates its game-over rule. Observation
work differs: Rust builds its full `Observation`; C++ builds a 252-feature
vector. Those measurements stay in the CSV files as separate diagnostics.

The supplied-TAKE result is narrow and had one strong concurrent workload on
the shared host. At 2026-10-05 03:08 UTC, system load averages were 3.61, 5.40,
and 6.60. The pinned AlphaZero search service used about 90% CPU, with a game
worker active. The benchmark ran sequentially and was not isolated from that
work. Treat the results as a bounded interface measurement, not a stable
hardware ranking.

The corrected files are `fixtures-corrected.txt`, `rust-results-corrected.csv`,
`ahin-results-corrected.csv`, and their run logs. The earlier
`pre-id-fix-ahin-*` files record the rejected market-ID run. They are retained
as invalid evidence and are not used here. See `RUN.json` for commands, tool
versions, and hashes.
