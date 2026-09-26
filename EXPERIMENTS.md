# Experiments

Experiments run on 2026-09-25. Opponents and weights are fixed within each run. All fixed-iteration comparisons rotate seats on identical setups. Each setup is an independent statistical block. See [docs/results/index.json](docs/results/index.json) for exact counts, seeds, intervals, runtimes, and record-set hashes. Compressed full per-game reports are kept beside their summaries.

## E1 — Failed long-range heuristic

**Hypothesis:** Rewarding progress toward high-prestige visible cards will beat a policy that buys any useful affordable card.

**Change:** Initial `strong-v0` used point weight 130, bonus value 100 with diminishing returns by bonus count, and token-taking scores based on distance reduction toward the best visible card. Purchases did not have a fixed preference. Opponent: greedy. Two players, master seed 101, 1,000 games (500 setups), four threads.

**Result:** 58 wins in 994 completed games; 6 games reached the decision cap. The conditional win credit was 5.84%. This candidate failed decisively and was rejected. It could postpone cheap engine purchases for too long. The exact reverse patch is [docs/strong-v0.patch](docs/strong-v0.patch); apply it only in an isolated copy for historical research.

## E2 — Efficient purchases and near-term targets

**Hypothesis:** Buying useful affordable cards promptly and reducing the cost of near-term targets will improve strength and avoid the observed cycles.

**Change:** `strong-v1` adds a purchase preference of 1,000, uses point weight 150, starts bonus value at 300 with diminishing returns by total card count and color concentration, penalizes token expense, and normalizes target potential by both remaining deficit and discounted cost. Noble progress contributes to purchase value. Payment and return decisions retain useful tokens.

**Screen:** Same seed start 101, expanded to 2,000 games, two players. All games completed. Win credit: 60.80%. No further weight tuning used the confirmation set.

**Confirmation:** Fresh master seed 9,000,001; 20,000 games, 10,000 paired setups. Win credit: **62.06%**, two-sided 95% CI **[60.92%, 63.20%]**. All games completed. Retain v1.

**Independent workflow check:** The actual promotion script used screen seed 12,345 and confirmation seed 1,000,012,345. Its 20,000-game confirmation returned **61.51%**, CI **[60.36%, 62.66%]**, with all games complete. It passed the one-percentage-point improvement margin. The script emitted `promote` without changing source.

## E3 — Baselines and multiplayer transfer

- Greedy vs random: seed 101, 2,000 two-player games. Greedy won 1,992 of the 1,999 completed games. One game was blocked by the rules gap.
- Strong vs random: seed 3,000,001, 2,000 two-player games. Strong won all 1,999 completed games. One game was blocked.
- Strong vs two greedy identities: seed 3,000,001, 3,000 games. Strong earned 48.37% conditional win credit, compared with an equal-seat baseline of 33.33%. One game was unfinished.
- Strong vs three greedy identities: same seed start, 4,000 games. Strong earned 43.71% conditional win credit, compared with 25%. One game was unfinished.

These are useful baseline measurements, but none of these incomplete runs qualifies for automatic promotion. Full summaries bound the missing outcome in the confidence interval instead of discarding it. Average score, rank, shared wins, and turns are in the JSON reports. No multiplayer Elo inference is made.

## E4 — Search budget

**Hypothesis:** Root action sampling with hidden-state determinization and short heuristic rollouts will improve action selection.

**Implementation:** Flat UCB search. Top six heuristic main actions, eight completed-turn rollout horizon, independent hidden-state sample per simulation, strong rollout policy, engine-aware leaf evaluation. Search acts through the public observation API. Opponent: strong. Two players, master seed 100,001, 1,000 games per screen, four threads.

| Simulations per decision | Search win credit | Two-sided 95% CI |
|---|---:|---:|
| 32 | 59.20% | [52.11%, 66.29%] |
| 128 | 72.50% | [66.06%, 78.94%] |

**Confirmation:** 128 simulations, fresh master seed **70,000,001**, **20,000 games**. Every game completed. Search earned **72.17%**, CI **[71.08%, 73.26%]**, against strong. The run took 199.58 seconds with four arena threads; other verification work overlapped part of that run. Retain search as a stronger, more expensive baseline. Do not compare its strength to a heuristic as if their compute budgets were equal.

## E5 — Rollout and leaf ablations

Same 1,000-game screen set, seed 100,001, 32 simulations, depth eight, width six. These screens are exploratory and share seeds.

| Rollout / leaf | Search win credit | Conclusion |
|---|---:|---|
| Random / engine | 42.80% | Reject as the default; faster but loses to strong |
| Greedy / engine | 53.75% | Inconclusive at this sample size |
| Strong / score only | 44.80% | Inconclusive versus strong; poor screen result |
| Strong / engine | 59.20% | Keep current defaults for this search family |

Random rollouts cost less per simulation. The comparison does not establish the best policy at equal wall-clock compute. The selected strong/engine configuration received the separate E4 confirmation; the alternatives did not.

A 1 ms soft budget, 1,000,000 iteration ceiling, one arena thread, and 200 games on seed 100,001 produced 71.50% win credit. This run is explicitly non-reproducible and the interval is broad. It is a timing smoke test, not promotion evidence. Its exact selected actions can still be saved and replayed by `play`.

## E6 — Profile-driven cache change

**Hypothesis:** Recomputing the same base target potential for every candidate wastes most of search time.

**Evidence:** A five-second macOS CPU sample of the 128-simulation confirmation placed `potential` at the top of the active stack 10,750 times, far above action application (100) and legal generation (577). This is sampling evidence, not an instruction-count measurement.

**Change:** Compute the unchanged base potential once per heuristic decision. Compute root candidate scores once before sorting. Keep the original integer arithmetic and stable tie order.

**Correctness:** All records, outcomes, and trajectory hashes match the uncached agent over **20,000 strong/greedy games** and **1,000 search/strong games**. The cache changes no selected action on those sets. Tests and lint pass. Controlled timing repeats and the retained decision are documented in [BENCHMARKS.md](BENCHMARKS.md).

## E7 — Simulator stress audit

Master seed 81,000,000, four threads, nominal count 1,000,002. To keep every seat block complete, the audit ran 333,334 two-player, 333,333 three-player, and 333,332 four-player trajectories: **999,999 total**. Each game seed is derived by the documented arena formula after adding player-count × 1,000,000 to the master seed.

**Result:** 890,430 normal completions, 109,569 no-action positions, zero decision-cap cases, zero invariant failures. This confirms broad transition safety; it does not prove every legal policy terminates. See the complete console report and the checked-in blocked replay fixture.

## Evidence archive maintenance

`scripts/collect_evidence.py` archives new reports from `results/` and
`results/promotion/`. It keeps prior index entries when their raw inputs are
absent. An empty input set leaves the archive unchanged. A repeated report is
idempotent. If an existing name refers to different raw bytes or record hashes,
the script rejects the entire input batch before writing it. Use a new name
for a new experiment, including a timing repetition. `--input` and `--output`
allow checks in separate directories.

A regression test reproduced the old failure: with no inputs, the script
replaced a nonempty index with `[]`. The fix also prevents an input with a
reused name from silently replacing the original raw evidence. Archive tests
use a real checked-in paired report and temporary output directories.

## Promotion workflow checks

Each promotion run now needs an unused output directory. `run.json` records
the parameters and confirmation seed before checks start. A failed command
writes an explicit rejection. The gate rejects non-finite throughput and
invalid confidence intervals. Final decisions include raw-report and
record-set SHA-256 identifiers. Prior evidence is never deleted for a retry.
The caller must still choose fresh confirmation seeds for each new candidate;
a new directory alone does not make reused seeds a fresh holdout.

A real smoke run used strong against strong, 20 screen and 20 confirmation
games, seed 96,000,000, and one thread. All 40 comparison games completed;
each identity received 50% credit. The gate correctly retained the baseline.
These small samples test the workflow and do not establish agent strength or
throughput. Parameters, decision, hashes, and compressed reports are in
`docs/results/gate-smoke.json` and its linked archives.

## E8 — Sparse owned-card scans

**Hypothesis:** Hidden-state sampling and invariant checks spend unnecessary
work scanning all 90 card IDs for each player, most of which are not owned.

**Change:** Iterate owned set bits in ascending card-ID order, with no change
to RNG calls or validation rules. Fixed opening and turn-40 benchmarks showed
35–43% lower sampling time and 29–59% lower invariant-check time. See
[BENCHMARKS.md](BENCHMARKS.md) for workload, estimates, and limits.

**Equivalence:** All 1,000 search/strong records at master seed 97,000,000,
128 iterations, depth 8, width 6, and one thread matched exactly. Both versions
reached the same no-action position in block 12, rotation 0, setup seed
18,210,048,530,404,438,792. It has no ranks or winners. Therefore this run
cannot promote an agent. Retain the core optimization based on the measured
operations and unchanged records, not on a strength claim.
