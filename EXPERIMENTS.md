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
Before computing confidence intervals, the archiver checks record counts,
ordered seat rotations, distinct setup blocks, per-block seeds, completion
totals, ranks, and winners. Incomplete games must have no ranks or winners.
A truncated record list cannot retain an unchanged requested-game count.
All historical report archives passed these checks without modification.

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

## E9 — Failed blocked-rollout penalty

**Evidence:** The E8 replay ends when search takes the last colored bank token,
leaving strong with three reservations and no affordable card. The scores are
8 and 4. Current search evaluates unfinished rollout leaves by relative score,
bonuses, and tokens, so a blocked position can have positive heuristic value.
The exact version-1 replay is `crates/splendor-arena/tests/fixtures/blocked-search-v1.json`.

**Hypothesis:** Assigning zero heuristic utility to a nonterminal rollout leaf
with no legal action will reduce this failure mode without reducing strength
against the existing search policy at the same simulation budget.

**Candidate:** A separate `search-avoid-blocked` identity. The existing `search`
policy stays available and unchanged. The candidate checks legal availability
at a main-phase leaf, including the depth boundary. Zero utility is a policy
penalty, not a game outcome or a claim that either player lost.

**Protocol, fixed before implementation:** First replay the known failing setup
as a development probe; it is not confirmation evidence. Then use the promotion
gate for 2,000 screen games against `search`, master seed 98,000,000, and a
20,000-game confirmation at seed 1,098,000,000 if the screen passes. Two players,
four threads, 128 simulations per decision, depth 8, width 6, strong rollouts,
engine evaluation, no wall-clock cap. Both policies have the same simulation
budget; extra leaf checks can change wall-clock cost. No tuning on confirmation
results. Any incomplete run prevents promotion. Record failure as well as success.

**Development probe:** The known blocked setup completed at 16–12 with the
candidate. This was a development check, not confirmation.

**Screen result:** 1,943/2,000 complete, six no-action positions, and 51 decision
limits. Conditional candidate credit was 50.15%; the unconditional 95% interval
was [44.48%, 55.79%]. The promotion gate rejected the run and did not use the
confirmation seeds. The candidate was removed from active code. Its forward
patch is `docs/e9-avoid-blocked.patch`; apply only for historical reproduction.
The raw report, summary, and probe replay are in `docs/results/e9-*`.
**Matched control:** Original search against itself, same seeds and budgets,
also had 1,943 completions, six no-action positions, and 51 decision limits.
The candidate did not reduce the number of unfinished games in this screen.
This identifies a baseline self-play limitation; the failures cannot be
attributed to the candidate alone. The control report is retained beside the
candidate report. Confirmation was not run, and the candidate was rejected.

**Capped control replay:** Setup seed 3,717,527,058,913,988,934, rotation 0,
reproduced 20,000 decisions with invariant checks and trajectory hash
`0f0d8df6a15de62a`. It has 10,017 completed turns and no outcome. The last 100
decisions alternate taking one green and one black token, then returning those
same tokens. Both players have three reservations. This is a legal no-progress
cycle, not a conservation failure. The full version-1 history is preserved in
`docs/results/search-selfplay-cap-v1.json.gz`.

At these repeated positions, search can have only one main action and delegates
return choice to the static strong heuristic. The E9 no-action penalty does not
address a cycle with legal actions. A future candidate should test a response
to repeated return positions, with observation-only memory and separate fresh
screen/confirmation seeds. No such candidate is retained yet.

## E10 — Repeated-return escape: partial improvement, rejected

**Hypothesis, before implementation:** A bounded memory of repeated return
observations can break the observed take-and-return cycles without changing
ordinary search decisions. On a repeated return position, choose a different
legal return bundle using a separate seeded RNG. This changes policy only;
there is still no forced pass, forced progress rule, or invented outcome.

**Candidate:** `search-return-escape`, wrapping the unchanged search policy.
Keep the last 16 return observations, ignoring only the completed-turn counter.
All other public information and the agent's own private information remain in
the comparison. On an exact repeat with more than one legal return, select
uniformly among alternatives to the default return. Do not change rollouts or
combine this with the rejected E9 penalty. The memory and RNG are agent-local.

**Protocol:** Use the known capped setup 3,717,527,058,913,988,934 as a development
probe. Run original search self-play and a 2,000-game candidate/search screen
at fresh master seed 99,000,000. Use `scripts/promote.py`; run 20,000 confirmation
games at 1,099,000,000 only if the screen passes. Two players, four threads,
128 iterations, depth 8, width 6, strong rollouts, engine evaluation, and no time
cap. Record completion categories and paired outcomes. No changes based on
confirmation results. Any incomplete run prevents promotion.

**Development result:** The known capped setup completed at 15–9 after 118 turns
and 193 decisions. This is a development probe, not confirmation.

**Fresh screen:** Candidate/search completed 1,990/2,000 games: six blocked and
four capped. The original-search self-play control completed 1,940/2,000:
seven blocked and 53 capped. Paired records show 49 capped games and one blocked
game became complete. All 1,940 completed control games remained complete.
Candidate conditional win credit was 51.71%, with unconditional 95% interval
[47.15%, 56.24%]. This does not establish a strength improvement.

**Decision:** Reject under the complete-run promotion rule. Confirmation was
not run; seed 1,099,000,000 remains unused. Remove the candidate from active
agents. Preserve its forward patch (`docs/e10-return-escape.patch`), focused
candidate test (`docs/e10-return-escape-test.rs`), full reports, paired status
counts, and probe history under `docs/results/e10-*`. Apply the patch to
commit `566d253` to reproduce its agent source. The active replay regression
checks the natural four-decision cycle without changing any game rule.

### E10 capped-state audit

All four remaining capped games reproduce the archived records exactly,
including their trajectory hashes. Each reaches the same normalized return
observation on thousands of consecutive candidate turns. Return exploration
changes the discarded color, but the next main decision still chooses a token
take while several legal purchases exist. The last eight decisions show three
to five purchase alternatives at each sampled candidate main phase. Increasing
return memory would not address these immediate repeats.

To reproduce: check out `566d253`, apply `docs/e10-return-escape.patch`, copy
`docs/e10-cap-audit.rs` to `crates/splendor-arena/examples/cap_audit.rs`, and run
`cargo run --release --locked --example cap_audit`. The harness records exact
block/rotation/setup seeds, uses the screen's 128/8/6 search budget, checks
invariants, and prints repeat distances and final legal choices. Output is in
`docs/results/e10-cap-audit.txt`; four full histories are `e10-cap-*-v1.json.gz`.
This is diagnosis on development evidence, not an independent strength test.

## E11 — Main-phase cycle escape hypothesis

**Hypothesis, before implementation:** Extending E10 with memory of repeated
main-phase observations can escape cycles that return-only exploration cannot.
If the default search chooses a token take on an exact repeated main observation
and a purchase is legal, select the strongest heuristic purchase. Keep all
legal actions in the engine. This is an agent policy, not a forced-progress rule.

**Candidate:** `search-cycle-escape`. Keep separate last-16 observation histories
for main and return phases, ignoring only completed turns. Keep E10's return
exploration and independent seeded RNG unchanged. On a repeated main position,
replace a preferred take with the highest-scored legal purchase if one exists.
Otherwise retain original search. Do not change rollouts, evaluation, or payment
choices. Both histories use only the acting agent's observation.

**Protocol:** Use E10's four capped games as development probes. Then run a
2,000-game candidate/search screen and original-search self-play control at new
master seed 101,000,000, with 128 iterations, depth eight, width six, two players,
four threads, and no clock budget. Use `scripts/promote.py`; confirmation is
20,000 games at 1,101,000,000 only if screening permits it. Report all incomplete
categories and paired changes. Reject any incomplete promotion run. Do not tune
on confirmation results. This test can show a completion benefit conditional on
these opponents and budget; it cannot prove termination.

**Development result:** All four E10 capped games completed in 58–82 turns
(86–131 decisions). These reused positions are diagnostic probes only.

**Fresh screen result:** Candidate/search completed 1,999/2,000 games, with no
caps and one blocked game. Original-search self-play on the same seeds completed
1,951, with 48 caps and the same one blocked game. Every completed control game
remained complete; all 48 capped control games became complete. Candidate win
credit among completed games was 49.95%, with unconditional 95% interval
[45.56%, 54.33%]. This does not establish a strength improvement.

**Remaining failure:** Block 30, rotation one, setup 811,391,511,434,643,069
reaches the same blocked record under both policies: trajectory
`492d8eb9732382b7`, 29 turns, 39 decisions, scores 3–2, and no winner. The
candidate had only one return phase, so no repeated-return override occurred.
The last two candidate main decisions had only one legal action. This is a
separate early blocking failure, not a residual capped cycle. Its full history
and final-choice audit are archived under `docs/results/e11-blocked-*`.

**Decision:** Reject because the screen is incomplete. Confirmation was not run;
seed 1,101,000,000 remains unused. The candidate is removed from active code.
The raw reports, summaries, paired categories, and gate decision are archived
under `docs/results/e11-*`. Source fingerprint: `16c5a89309314fa9`. Apply
`docs/e11-cycle-escape.patch` to `b370f17` to reproduce the agent source. The
archived probe harness and focused candidate tests are in `docs/e11-*.rs`.
A permanent replay test now shows that a legal token cycle can repeat even when
purchases are affordable. The engine still preserves that choice and gives no
winner to the cycle.

## Record-based promotion gate check

The gate now checks raw game records, stage settings, setup seeds, and source
continuity, then recomputes the candidate confidence interval. It rejects a
fabricated interval even if that interval would otherwise pass the promotion
threshold. A regression test confirms that such a screen cannot run confirmation.
The evidence tools have their own hashes because the Rust source fingerprint
does not identify Python decision logic.

Two workflow smoke runs used strong/strong, 20 screen and 20 confirmation games,
two threads, and fixed default search settings. Master seeds were 102,000,000
and 102,000,100; confirmation seeds were 1,102,000,000 and 1,102,000,100. All games
completed. Both stages in both runs gave 50% credit with interval [0, 1]; the
gate correctly retained the baseline. These are workflow tests, not agent
strength evidence. The second run also checks script fingerprints. Reports,
manifests, and decisions are under `docs/results/record-gate-*`.

All 21 Python tests passed, including shared-win clustering, incomplete-outcome
bounds, interval corruption, record truncation, wrong setup seeds, changed
sources/settings, and prior evidence preservation. Both real gate runs also
passed formatting, strict workspace Clippy, and all 51 release Rust tests.

## E11 blocked-return branch audit

An exhaustive local audit checked whether the sole E11 blocked screen game
could avoid the block by changing its first return. This is a diagnosis of one
recorded game, not a new agent experiment. The full archived history passes
replay validation before the audit truncates it at decision 37.

All five legal returns have four complete opponent replies. In each case, taking
the returned token leaves the candidate with no legal action. The other three
replies are purchases; each leaves the candidate with one legal purchase and
at least one token action. Thus all 20 paths are checked, five end in a block,
and none gives a terminal outcome. No return choice guarantees continued play.
This evidence does not support a return-only change for this failure. The
opponent's choice also matters; these branch counts are not probabilities.

The maintained `return_audit` example checks every transition invariant and
records complete reply paths and next legal actions. Decompress
`docs/results/e11-blocked-v1.json.gz` to `/tmp/e11-blocked.json`, then run:

```sh
cargo run --release --locked --example return_audit -- /tmp/e11-blocked.json 37
```

`docs/results/e11-return-audit.json` records the results, production source
fingerprint, diagnostic source hash, and input archive hash. Rules and agents
are unchanged. The next useful diagnosis is the earlier Main choice at decision
32, where the candidate still had five legal takes.

## E11 earlier Main decision audit

The next audit starts before decision 32 in the same recorded game. It checks
all legal branches within seven and ten decisions, including payment, return,
and noble decisions. The actor chooses to avoid its own block; the opponent
chooses to cause it. A nonterminal state with no legal actions is a block. A
horizon cutoff is unresolved and receives no winner or claim of lasting safety.

| Take | Opponent can force actor block by 7 decisions | By 10 decisions | Actor-blocked leaves at 10 |
| --- | --- | --- | --- |
| White, blue, red | No | No | 4 |
| White, blue, black | No | No | 0 |
| White, red, black (recorded) | Yes | Yes | 19 |
| Blue, red, black | No | No | 8 |
| Two white | Yes | Yes | 12 |

The seven-decision audit visits 12,218 states; the ten-decision audit visits
1,058,779. Counts include repeated states on distinct paths and are not branch
probabilities. Every applied transition passes invariants. The full recorded
history is verified before truncation. No terminal state occurs in either tree.
The earlier choice is therefore material to this specific failure, unlike the
later return choice. This does not establish agent strength or eventual game
completion for any alternative.

This is privileged offline analysis with the recorded hidden deck and complete
states. It does not establish a strategy that works across unknown decks. Any
agent feature must be computed from Observation and tested with independent
seeds. No agent change is made here. The maintained `block_audit` example has
explicit horizon and node limits; exhausting its node limit fails the run
without an exhaustive-result claim.

```sh
cargo run --release --locked --example block_audit -- crates/splendor-arena/tests/fixtures/blocked-e11-v1.json 32 7
cargo run --release --locked --example block_audit -- crates/splendor-arena/tests/fixtures/blocked-e11-v1.json 32 10
cargo test --release --locked --example block_audit
```

Results and source/input hashes are in `docs/results/e11-main-audit-{7,10}.json`.
Two diagnostic regression tests distinguish cutoffs from blocks and check the
five root alternatives. Formatting, strict release all-target workspace Clippy,
all 53 release workspace tests, and both diagnostic tests pass.

## E12 hypothesis: preserve an affordable purchase under token scarcity

Before any E12 agent change: the observation-only audit of E11 decision 32
shows that all three takes which avoid a forced block within ten decisions
make visible card 18 affordable. The two takes that permit a forced block make
no target affordable. Existing strong heuristic scores are 125, 132, 60, 132,
and 0 in enumeration order; search selected the third action despite its lower
heuristic score. The token feature uses only the current Observation.

Hypothesis: when the player has three reservations, all legal root actions are
takes, and at most ten colored tokens remain in the bank, restrict search to
takes that make at least one visible or own reserved card affordable without
requiring a return, if such a take exists. This may reduce blocks caused by
token hoarding without reducing playing strength. A visible card can still be
bought by an opponent; this filter is not a proof of future legal play.

Candidate `search-affordable` will use this root filter only. Rollout choices,
reward, evaluation, search depth, and original `search` remain unchanged. This
is distinct from E9's failed blocked-leaf reward penalty and does not restore
E10/E11 cycle logic. The known E11 history is a development probe only.

Use `scripts/promote.py`: candidate against search, two players, 2,000 screen
games, seed 105,000,000, four threads, 128 iterations, depth 8, width 6. If the
gate allows confirmation, use 20,000 games and fresh seed 1,105,000,000. Report
all incomplete games and retain no strength claim without gate evidence.
