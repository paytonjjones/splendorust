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

### E12 result: rejected

The observation-only audit is saved in `docs/results/e11-token-audit.json`.
The new `token_audit` example records all target deficits, bank supply, and
existing heuristic scores before any return. It marks returns as required
rather than claiming that all collected tokens can be kept.

The development probe selected an affordable-card take for all 32 independent
agent RNG seeds, with identical choices on repeat. The full known blocked game
then completed at 78 turns and 122 decisions, scores 9–16. This is a reused
development case, not confirmation evidence.

The fresh 2,000-game screen completed 1,968 games, with 29 caps and three blocks.
Candidate completed-game credit was 51.42%; the unconditional interval was
[46.39%, 56.39%]. The same-seed original-search control completed 1,966 games,
with 31 caps and three blocks. Paired results: 1,963 games completed in both,
26 were capped in both, all three blocked games stayed blocked, five control
caps became complete, and three control completions became capped. The small
net completion gain therefore includes regressions and proves no strength gain.

The gate rejected the incomplete screen. Confirmation seed 1,105,000,000 was
not used. The candidate was removed from active source. Reproduce it by applying
`docs/e12-affordable.patch` to `6654cbf`; candidate production fingerprint is
`37d082b07f81f7f7`. The probe source is `docs/e12-probe.rs` (copy to the arena
examples directory to run it). Raw reports, summaries, paired statuses, probe
history, run settings, and gate decision are archived under `docs/results/e12-*`.

Both candidate and restored baseline passed formatting, strict workspace
all-target Clippy, and all 53 release workspace tests. No rules or replay
semantics changed; ENGINE_VERSION remains `splendorust-v1`.

### E12 newly capped games: exact recurrence diagnosis

Reconstructed the candidate at `6654cbf` plus its archived patch in a temporary
worktree. All three newly capped games match every archived record field,
including trajectory hashes, under source `37d082b07f81f7f7`. Invariants were
checked during play and replay. Each run stops at 20,000 decisions without an
outcome.

| Block | Rotation | Repeating suffix starts at decision | Decisions in suffix | Candidate purchases available in cycle |
| --- | --- | --- | --- | --- |
| 179 | 0 | 87 | 19,913 | 5 |
| 444 | 1 | 75 | 19,925 | 3 |
| 927 | 1 | 91 | 19,909 | 5 |

Each cycle has four decisions and two completed turns. Both players repeatedly
take and return one red token in blocks 179 and 444, or one black token in block
927. The opponents also have affordable purchases: five, five, and four,
respectively. A full period preserves both players' observations except the
turn count. Its actions move tokens only, so the hidden decks and card locations
cannot change. No winner is assigned.

An initial action-only period detector proposed a two-decision period, but the
observation equality assertion rejected it because the active player changed.
The saved diagnostic requires both action repetition and observation equality;
this identifies the four-decision state cycle. This failed diagnostic assumption
is not counted as evidence for a shorter cycle.

E12's only-takes condition is false in every Main phase in these cycles. Thus
the filter changed earlier play but has no effect once these positions recur.
This is the same purchase-avoidance pattern diagnosed in E10/E11, not a new rule
failure. It supports testing recurrence handling as a separate intervention;
it does not establish that combining rejected candidates improves strength.

The three full histories and a fingerprinted audit are saved under
`docs/results/e12-cap-*`. To reproduce, apply the E12 patch to `6654cbf`, copy
`docs/e12-cap-audit.rs` into `crates/splendor-arena/examples/e12_cap_audit.rs`,
decompress the E12 screen report, and run:

```sh
cargo run --release --locked --example e12_cap_audit -- /tmp/e12-screen-replay.json /tmp/e12-cap-histories-new
```

The output directory must be new. The harness checks the production fingerprint
and exact archived records before reporting recurrence evidence. Formatting,
strict release all-target workspace Clippy, and all 53 release workspace tests
pass in this historical candidate checkout. The main branch remains unchanged
apart from research records; its standard suite includes 55 tests after the
later example-test configuration change.

## E13 hypothesis: combine scarcity filtering and recurrence handling

Before changing agents: E11 greatly reduced capped games but left one early
block. E12's observation-only affordability filter completed that known blocked
probe, while its three new screen caps were all repeated token cycles with
legal purchases. Its filter is inactive in those cycles. These mechanisms act
at different observed failures, which supports a controlled combination test.
It does not establish that either mechanism improves playing strength.

Candidate `search-combined` will apply E12's exact root affordability filter
inside E11's exact observation-only cycle wrapper. Keep the same 16-position
Main/Return memories, normalized turn counter, separate return RNG, and
purchase selection on repeated Main positions. Do not change reward, rollout
policy, evaluation, core rules, or baseline search. This is a combination test,
not a new tuning pass on the old screen seeds.

Use the known E11 block and three new E12 caps as development probes only.
Use `scripts/promote.py` against original search: two players, 2,000 screen
games, fresh seed 106,000,000, four threads, 128 iterations, depth 8, width 6.
Use 20,000 confirmation games with seed 1,106,000,000 only if the gate permits.
Run same-seed search/search as a completion control. Report regressions and
unfinished games, and remove the candidate if rejected.

### E13 result: rejected

The first integration attempt stopped before any games: overlapping archived
patches left the new agent name unregistered. Both candidate legality/privacy
tests failed, and the gate recorded an execution failure. Those run and decision
records are retained as `e13-integration-failure-*`; no screen seed was consumed.
The corrected combination then passed those tests and both recurrence tests.

All four development probes completed. The known E11 block finished in 78 turns;
the three E12 cap regressions finished in 66, 88, and 84 turns. At the known
scarcity position, all 32 tested agent seeds chose an affordable-card take and
repeated their choices exactly. These are reused probes, not fresh strength
evidence.

The fresh screen completed 1,994/2,000 games, with zero caps and six blocks.
Candidate completed-game credit was 51.48%, with unconditional interval
[47.04%, 55.91%]. The same-seed original-search control completed 1,948 games,
with 48 caps and four blocks. Paired categories: 1,945 completed in both; all
48 control caps became complete; one control block became complete; three
blocks stayed blocked; and three control completions became blocked.
Thus recurrence handling has a clear completion effect in this workload, but
the combined policy also introduces blocking regressions and proves no strength
gain. No broader opponent or compute-budget claim follows.

The gate rejected the incomplete screen. Confirmation seed 1,106,000,000 remains
unused. The candidate was removed from active source. Apply
`docs/e13-combined.patch` to `bb68482` to reproduce production fingerprint
`bc5ac15a9e3914a2`. Probe and focused test sources are saved as `docs/e13-*.rs`;
copy them back to their respective arena examples/tests directories to run.
All raw reports, paired categories, gate decisions, settings, and four complete
probe histories are under `docs/results/e13-*`.

The corrected candidate passed formatting, strict all-target workspace Clippy,
and 57 release workspace tests including its two focused recurrence tests.
The restored baseline passed formatting, strict all-target workspace Clippy,
and its 55 release workspace tests. The normal release binary was rebuilt.
No rules, engine version, or replay semantics changed.

### E13 new blocks: scarcity-filter regressions

Reconstructed E13 at `bb68482` plus its saved patch. All three newly blocked
candidate records and their completed controls reproduce exactly, including
trajectory hashes, under source `bc5ac15a9e3914a2`. Invariants pass throughout.
All three blocks affect candidate identity 0.

| Block | Rotation | First differing decision | Only scarcity trigger | Newly affordable card | Candidate buys it at decision | Blocked after decisions |
| --- | --- | --- | --- | --- | --- | --- |
| 223 | 1 | 34 | 34 | 4 | 36 | 49 |
| 237 | 0 | 29 | 29 | 35 | 35 | 43 |
| 855 | 1 | 41 | 41 | 35 | 44 | 64 |

In each history, the candidate has exactly one scarcity-filter event and no
repeated Main or Return observation in the wrapper's 16-position memories.
The first action divergence from the control is at that filter event. Therefore
these histories implicate the affordability filter, not a cycle-escape choice.
The newly affordable target is a visible card in all three cases. The candidate
buys it before eventually blocking, so opponent removal of that card is not the
explanation. Immediate affordability alone does not ensure later access to legal
moves. This is a limit of the filter's premise, not a new engine-rule failure.

The audit records both full histories, public token features, condition events,
later purchases, and the last eight decisions. Input, source, and history hashes
are in `docs/results/e13-block-audit.json.gz`; full histories are under
`docs/results/e13-block-*-v1.json.gz`. To reproduce, restore the candidate,
copy `docs/e13-block-audit.rs` to the arena examples directory, decompress the
E13 screen/control reports, and run:

```sh
cargo run --release --locked --example e13_block_audit -- /tmp/e13-screen-replay.json /tmp/e13-control-replay.json /tmp/e13-block-histories-new
```

The output directory must be new. The historical candidate passes formatting,
strict release all-target workspace Clippy, and all 55 release workspace tests.
No new agent intervention is justified solely by these three reused cases.
The active baseline and engine rules remain unchanged.

## Search depth arithmetic audit

Hypothesis: a search depth of `u32::MAX` overflows the absolute turn limit
once play has started. Comparing elapsed rollout turns with the requested
depth will remove this overflow and preserve all ordinary depth decisions.
This is a numeric correctness change, not a strength candidate. Validate a
legal position at turn one with large depths, then compare fixed-budget arena
records before and after the change. No claim of improved playing strength is
planned. Core turn-counter exhaustion remains a separate limit.

The regression failed before the change in debug (integer overflow) and release
(different chosen action). Both failure logs are in `docs/results/search-depth-*-before.txt`.
The elapsed-turn check passes for eight fixed agent seeds at a legal turn-one
position, comparing depth 1024 with `u32::MAX`. The paired 100-game search/strong
run at setup seed 109,000,000, 16 iterations, depth 8, width 6 has identical full
game records before and after; all games complete. Reports and hashes are in
`docs/results/search-depth-{before,after}.json.gz` and
`docs/results/search-depth-comparison.json`. Source changes from
`3992ef689453dcc8` to `8046abddb9a4d723`. Timing from this small run is not a
performance result. No strength promotion is claimed.

## Counter-capacity search handling

Hypothesis: stopping a rollout at the engine counter capacity prevents a
resource-limit panic without changing ordinary fixed-budget search decisions.
At a root already at capacity, select the usual heuristic legal action; the
core caller receives the explicit resource error. At a rollout boundary, use
the existing nonterminal evaluation, never a fabricated outcome. Validate the
boundary directly and compare a fixed seed workload with the prior build.

The capacity tests pass. A fixed 1,000-game search/strong comparison at seed
110,000,000, 64 iterations, depth 8, width 6 and four threads has identical full
records: all 1,000 games complete. Before source `ae728260bd1abd30` uses v1;
after source `93aa7293171a9875` uses v2. Both reports and hashes are archived in
`docs/results/capacity-{before,after}.json.gz` and `capacity-validation.json`.
This is behavioral regression evidence, not a playing-strength promotion or
performance claim. No failed boundary experiment is discarded: v1 debug and
release failure results remain beside the v2 resource-error results.

## E14 hypothesis: reuse base potential for Take scoring

The current v2 release profile (fixed 10,000 search/strong games, seed
112,000,000, 128 iterations, depth 8, width 6, four threads) still identifies
`potential` as the largest sampled application function. Source inspection
shows the strong Take branch recomputes `potential(o, p)` despite receiving the
already computed `base_potential`; visible reservation scoring uses that cache.
`git blame` shows the uncached Take expression predates this work, rather than
being a regression from the recent v2 changes.

Hypothesis: using the supplied base value, with the existing uncached fallback,
will preserve every integer score and action while reducing search runtime.
Before any edit, plan direct cached/uncached score equality across legal actions
and phases, all Rust checks, and alternating fixed-budget release comparisons
with exact record equality. Use a new workload seed for the clean timing runs;
the profiled run's elapsed time is not a throughput baseline. This is a
performance experiment, not a strength candidate or a change in game rules.

### E14 result: retain the cache reuse

The strong Take scorer now uses its supplied base potential, with the same
uncached fallback. A regression test compares cached and uncached integer
scores for every legal action over 96 seeded trajectories (2–4 players), in
both scoring modes, and requires Main, Payment, Return, and Noble coverage.
All 71 release workspace tests and strict release workspace Clippy pass.

Measured eight serial release runs on the same Apple M4 Pro/macOS 26.7 host,
Rust 1.98.1, Cargo.lock, and release settings. Screening uses ABBAAB order:
1,000 search/strong games per run, seed 116,000,000, 128 iterations, depth 8,
width 6, one thread, 20,000-decision cap, and no time budget. Baseline source
`5fbacedf05ec987b` has runtimes 28.675, 29.219, 29.354 seconds; changed source
`0bcb24bf9c705a56` has 22.976, 23.103, 23.326 seconds. Median runtime falls
20.9% (29.219 to 23.103 seconds), equivalent to 26.5% greater throughput.
All six runs complete all games and have identical full game records.

Fresh confirmation seed 1,116,000,000 uses the same settings: 29.453 to 23.354
seconds, a 20.7% reduction. Both builds have 999 completed games and one blocked
game; both exit 1. Their full records match, including the unfinished result.
No winner is assigned to that game. This is a score-preserving performance
change, not a strength promotion. The result is conditional on this machine,
opponents, and budget. Record equality does not claim saved action-trace
equality; exact score tests separately support unchanged decisions.

`docs/results/e14-comparison.json` records exact commands, settings, process
exits, source IDs, binary hashes, raw report hashes, and record-set hashes.
All eight full reports and process logs are archived as `e14-[0-7]-*`.
No rule, RNG, enumeration, or replay semantics changed; engine stays v2.

## E15 hypothesis: cache fixed target values across token alternatives

After E14, the fresh diagnostic sample still identifies potential as the largest
sampled application function. Each invocation scans up to 15 visible/reserved
targets and recomputes discounted cost and card worth. Take, Return, and gold
reservation scoring alter tokens but leave bonuses and owned cards unchanged.

Hypothesis: a fixed-capacity per-decision cache of target discounted costs and
card worth can reduce this repeated work without changing integer scores.
Keep the original potential calculation as an independent test oracle. Scope
cache use to token-only changes; a Payment changes bonuses/ownership and must
use newly derived values or the original path. Preserve target order, top-three
ranking, integer division order, hidden-information boundaries, and fallback
behavior. Use no heap allocation for this cache. Test every legal action across
seeded 2–4-player trajectories and every phase, including varied token/gold
holdings and owned-card exclusions. Run all required Rust checks, then serial
release comparisons and a fresh confirmation seed with exact record equality.
Keep the change only if the measured benefit supports its added complexity.
Planned fresh screening seed: 117,000,000; confirmation: 1,117,000,000. These
seeds have not been run for this hypothesis. No strength promotion is proposed.

### E15 result: retain fixed target cache

Implemented a stack-resident cache for up to 15 targets. It stores discounted
color costs, their total, and card worth times 20. Main token actions and Return
reuse it; Payment keeps the original calculation because ownership and bonuses
change. Integer division and top-three ordering are unchanged. The original
potential implementation remains the uncached path and score-test oracle.
The 96-trajectory all-action test now also checks cached base potential and all
cached action scores against that oracle. All 71 release Rust tests, strict
release workspace Clippy, and formatting pass.

Same Apple M4 Pro/macOS 26.7 host and Rust 1.98.1 release settings as E14.
Serial ABBAAB screening: 1,000 search/strong games, seed 117m, 128 iterations,
depth 8, width 6, one thread, 20,000-decision cap, no time budget. Baseline
source `0bcb24bf9c705a56` takes 23.509, 23.554, 23.589 seconds; changed source
`50400f40eb161b1a` takes 18.609, 18.662, 18.753 seconds. Median runtime falls
20.8% (throughput +26.2%). Fresh confirmation seed 1,117m takes 23.730 versus
18.744 seconds, a 21.0% reduction. All eight runs complete every game, exit 0,
and have identical full records within each seed, including trajectory hashes.

Retain the change. These are workload-specific performance measurements, not
a strength promotion or full simulator parity. Engine version stays v2.
`docs/results/e15-comparison.json` and `e15-[0-7]-*` retain exact commands,
settings, process status, binary/source/record hashes, all reports and logs.

## E16 hypothesis: a larger fixed search budget after cache improvements

E4 tested 32 versus 128 simulations; no retained experiment tests 256. E14/E15
reduced search cost without changing its scores. Hypothesis: 256 simulations
improve win credit against strong compared with 128, at increased compute cost.
No agent code or default will change for this experiment. This is a budget
comparison against a fixed opponent, not equal-compute policy evidence.

Protocol recorded before execution: paired two-player search/strong runs at
128 and 256 iterations, depth 8, width 6, strong rollouts, engine evaluation,
four threads, 20,000-decision cap, no clock budget. Screen each on 2,000 games
at fresh seed 121,000,000. If the conservative mean difference bound is positive
and 256 has no more unfinished games, run both budgets on 20,000 fresh games
at 1,121,000,000. Otherwise stop and record the screen. Keep all unfinished
outcomes, with candidate win credit bounded by [0,1], and cluster both seat
rotations per setup for paired differences. Report runtime separately.

Confirmation requires a positive paired 95% lower confidence bound to support
a benefit. Use bounded empirical Bernstein intervals on normalized per-setup
differences; with unfinished outcomes, use separate 97.5% intervals for lower
and upper credit bounds (Bonferroni gives at least 95% joint coverage). Never
assign a winner to unfinished games. Any unfinished run remains ineligible for
promotion. A strength promotion or default change would need the project gate;
this experiment alone will not make either claim.

### E16 result: conditional budget benefit, no promotion

Screen: both 2,000-game runs complete. Win credit against strong is 73.50% at
128 iterations and 77.20% at 256. Paired difference is +3.70 percentage points,
95% interval [-1.92, +9.32]. This passes the recorded screen rule but is not
confirmation by itself. The fresh 20,000-game comparison was then run.

Confirmation at 1,121m: 128 completes 19,999 games with one blocked game;
256 completes 19,997 with two blocked games and one decision-cap game. Both
processes exit 1 as designed. Unconditional candidate-credit bounds are
[73.315%, 73.320%] and [75.8775%, 75.8925%], respectively. The paired gain is
bounded by [2.5575, 2.5775] percentage points; its conservative paired 95%
interval is **[+1.04, +4.09] points**. This supports improved credit against
strong at the larger budget, with the unfinished outcomes fully included.
It is not a head-to-head result between search budgets or equal-compute evidence.

Runtime is 105.89 versus 210.34 seconds on this host (four threads, serial runs,
no overlapping build/tests). The larger budget costs about twice as much and
has more unfinished games. Do not promote or change defaults. No policy code
changed. The positive conditional strength result and negative completion
result are both retained.

New capped case: 256 iterations, block 1508, rotation 0, setup seed
11864268526903350202, 20,000 decisions. The two 256 blocked cases are blocks
992/rotation 0 and 5159/rotation 1; the 128 blocked case is block 7783/rotation 1.
These are development audit inputs now, not fresh future confirmation seeds.

`docs/results/e16-runs.json` retains exact commands, exits, source/binary hashes,
status counts and full record hashes. All four reports and process logs are
archived. `scripts/compare_budgets.py` validates paired configurations and seat
schedules, computes block-level difference bounds, and retains analysis/report
hashes. Its tests cover shared wins, rotation clustering, unfinished outcomes
and mismatched inputs. All 52 Python tests pass with the pinned reference.
Reproduce the confirmation analysis with:

```sh
python3 scripts/compare_budgets.py docs/results/e16-confirm-128.json.gz docs/results/e16-confirm-256.json.gz
```

### E16 capped-state audit

The 256-budget capped game reproduces the full archived record with invariant
checks: trajectory `bbd0114e285933e5`, 20,000 decisions, 10,010 turns, scores
3–3, no winner. From decision 51, 19,949 actions follow a period-four suffix:
strong returns one red token; search takes it; search returns it; strong takes
it. This advances two player turns. Search has two legal purchases at its Main
phase; strong has only the token take. One more full period is legal, preserves
all players' observations except turn count, and has no outcome. Because the
period has only token actions, hidden card order and ownership cannot change.

This is the same purchase-avoidance pattern as earlier cap audits, now on a
fresh larger-budget case. It is not a core termination defect or a proof that
the RNG-driven policy repeats forever. Do not restore rejected E10/E11 wrappers
from this one case. Source inspection also matters: simulated root-player
future turns use strong rollouts, while actual root decisions use search.
A repeated-state penalty inside rollouts might miss a cycle that this policy
difference creates. Inspect those simulated continuations before proposing it.

The reusable `cap_audit` example checks source/settings, replays each capped
record exactly, and writes histories to a new directory with block/rotation
filenames. No detected short token period is reported as unknown, not absence
of all recurrence. A four-player, one-decision-cap smoke produces four distinct
histories, no cycle claim, and no winner. Formatting, strict release all-target
Clippy and all 71 release workspace tests pass. Evidence and history hashes are
in `docs/results/e16-cap-validation.json`, `e16-cap-audit.jsonl`, and
`e16-cap-1508-v2.json.gz`. The example adds no production semantics or version
change; its own source hash is retained separately.

### E16 simulated-continuation diagnosis

At prefix 52 of the cap history, compare every legal root action on 256 common
sampled worlds (seed 123m), using strong rollouts and the current Engine leaf
arithmetic. This diagnostic uses the root observation, not the real future deck.
It is equal sampling per action, not a trace of production adaptive UCB visits.

| Completed-turn horizon | Take red | Buy market 0 | Buy market 3 |
|---|---:|---:|---:|
| 4 | 0.491977 | 0.484895 | 0.630305 |
| 8 | 0.618059 | 0.426508 | 0.578375 |
| 16 | 0.485598 | 0.343027 | 0.454168 |
| 32 | 0.063969 | 0.020723 | 0.040797 |

Values are mean diagnostic rewards, not win probabilities. In every sampled
world at every tested horizon, Take returns to the original root observation
after two turns, then the strong rollout buys. Immediate purchases do not
return to the root. None of these probes blocks; horizons 4/8/16 do not reach
terminal states. At horizon 32, 213/242/238 worlds respectively terminate.
The depth-eight estimate favors delay even though actual search repeats that
delay. Simply increasing the horizon is not a consistent solution in this probe.

This supports a specific mismatch: the simulated future root policy purchases
where the real root search postpones again. A detector that includes the initial
root observation can see this recurrence before the rollout purchase. No core
rule defect, eventual policy termination, or population strength claim follows.
`rollout_audit` preserves the first sampled trace per action and counts purchase
offsets, returns to root, terminal and blocked endpoints. Commands, source and
harness hashes are in `docs/results/e16-rollout-validation.json`; full outputs
are `e16-rollout-{4,8,16,32}.json`. Formatting, strict release all-target Clippy
and 71 release workspace tests pass. No agent code changed.

## E17 hypothesis: pessimistic value for a return to the root observation

Recorded before agent edits. E16 shows that a root Take can restore the exact
root observation two turns later in all sampled worlds, while the rollout then
buys. Hypothesis: giving zero search reward to such a simulated recurrence will
reduce purchase postponement and improve credit against the existing search
policy at the same fixed budget. This differs from E9's no-legal-action penalty
and E10/E11's actual-history action overrides.

Candidate `search-root-cycle`: compare the root player's observation at later
root Main phases with the initial observation after clearing only turn count.
On equality, stop that simulation and use reward zero as an agent heuristic.
Never change the core, legal actions, outcome, or arena completion status. Keep
ordinary `search` unchanged. A recurrence cannot become a declared game loss or
win. Do not use real setup seeds, decks, or hidden opponent reservations.

Development: use the E16 capped prefix/full game at 256 iterations; test that
only the candidate changes and that hidden-world permutations cannot affect
its choice. Then use the promotion gate against search: fresh 2,000-game screen
at 124m, 128 iterations/depth 8/width 6, four threads. Run matched search self-play
control on the same setups. Confirmation at 1,124m stays untouched unless the
screen qualifies under the gate. Retain failures, incomplete outcomes and timing
cost; no tuning on confirmation. Reject the candidate if it fails the gate.

### E17 result: development cycle solved, screen rejected

Candidate source `36c41eca9c6d8ede` assigns zero heuristic reward on a later
root Main observation equal to the initial observation except turn count. The
check runs before the horizon cutoff. It changes no core outcome. Ordinary
search retains its old behavior; the known full capped game still reproduces
trajectory `bbd0114e285933e5` exactly.

At the E16 prefix, 16 agent seeds at 256 iterations/depth 8 all choose Take for
search and BuyVisible(3) for the candidate. At depth 2 both choose that purchase.
Equivalent hidden-world observations give identical choices. In the full known
game against strong, the candidate finishes in 111 decisions/70 turns and loses
12–15; ordinary search remains capped at 20,000 decisions, with no winner.
Completing that probe is not evidence of a win or population improvement.

The real promotion gate's fresh 124m screen rejects the candidate: 1,942 of
2,000 complete, seven blocked and 51 capped. Conditional completed-game credit
is 51.36%; unconditional 95% bounds [45.57%, 57.06%]. The matched search/search
control has exactly the same completion counts and winning identities. Only
one full record changes (block 687, rotation 1), and its winner stays the same.
All 58 unfinished records are identical. Candidate/control runtime is
50.20/48.79 seconds; this single pair is descriptive, not a precise overhead
benchmark. Confirmation seed 1,124m remains unused.

Reject and remove the candidate. Its success against the strong-opponent probe
did not transfer to this search-opponent screen. Do not broaden its rule or tune
on confirmation in this experiment. The candidate patch is
`docs/e17-root-cycle.patch` against `b5dc58b`. Gate manifest, executable hash,
full screen/control records, histories, probe actions and failed decision are
preserved under `docs/results/e17-*`. `agent_probe` is a reusable diagnostic
for seeded action choices and equivalent hidden-world observations; it makes
no universal privacy or strength claim. After removal, formatting, strict
release all-target Clippy, 71 release workspace tests and 52 Python tests pass.
Engine stays v2; ordinary policies remain random/greedy/strong/search.

## E18 — Search transfer to three and four players

**Hypothesis, before runs:** The retained 128-iteration search policy earns
more than equal-seat win credit against two or three copies of strong. Earlier
multiplayer strength evidence concerns strong versus greedy; the E15 multiplayer
runs checked exact records and performance, not a fresh strength confirmation.

No agent change is proposed. Run the actual promotion gate with fixed 128
iterations, depth 8, width 6, strong rollouts, engine evaluation, four arena
threads, and a 20,000-decision cap. Use a one-percentage-point margin over
1/player_count. Three players: screen 3,000 games at master seed 132,000,000,
then 21,000 games at 1,132,000,000 if the gate proceeds. Four players: screen
4,000 games at 133,000,000, then 20,000 at 1,133,000,000 if the gate proceeds.
These seeds are reserved before execution. Keep all blocked and capped games;
an incomplete stage rejects promotion. Run the two gates in sequence. Results
are conditional on these opponents and this unequal search/heuristic compute
budget. No multiplayer Elo or universal strength claim is planned.

**Three-player result:** The screen has 2,999 normal completions and one
blocked game. Search wins 1,568 games: 52.28% conditional win credit, with
unconditional 95% CI [48.309%, 56.258%]. The gate rejects incomplete games
before confirmation. The blocked record is setup block 818, rotation 2, seed
11622764811484448866, at turn 61 / decision 86, scores 5/6/4, winner mask zero,
trajectory hash `1e4968871b4c2d80`. The confirmation seed 1,132,000,000 remains
unused. This screen shows conditional strength but does not pass promotion.

**Four-player result:** All 4,000 screening games complete. Search wins 1,579,
for 39.475% credit and 95% CI [35.996%, 42.954%]. The gate continues to the
fresh 20,000-game confirmation (5,000 setup blocks). All games complete.
Search wins 7,713, for **38.565%** credit and **95% CI [37.224%, 39.906%]**.
The lower bound exceeds the 26% threshold (25% equal-seat credit plus one
percentage point). The actual gate returns `promote`. No source or defaults
change: this is evidence for the existing policy at the stated budget.

Runtime is 15.66 seconds for the three-player screen, 20.73 seconds for the
four-player screen, and 105.55 seconds for confirmation on the current host.
The gates ran sequentially with no concurrent simulation or test workload.
These are run times, not a paired performance improvement claim.

Full compressed reports, gate logs, build and run manifests, and both decisions
are in `docs/results/e18-*`. `e18-summary.json` records raw and record-set
hashes, the exact blocked record, and intervals independently recomputed
from seat-rotation blocks. All reports pass `validate_report`. Both gates ran
formatting, strict workspace Clippy, and the 72 release workspace tests.
Source fingerprint is unchanged at `50400f40eb161b1a`. No multiplayer Elo,
equal-compute advantage, or guarantee against other opponents is claimed.

**Three-player block diagnosis:** The report record reproduces exactly with
invariants enabled and a saved v2 history. Search (identity 0, seat 1) is
blocked: the colored bank is empty, it has three reservations and no affordable
card. Four gold remain in the bank. There is no core terminal outcome.

Search's last decision, index 83, takes white/red/black. At that observation
the bank has 1/2/2/2/2 colored tokens, and all ten distinct three-color takes
are legal. Six alternatives make at least one current market card affordable
without a return; the chosen take does not. The subsequent two strong moves
empty the colored bank. The last move is the only one of its 16 alternatives
that immediately blocks the next player. These facts do not establish a
forced block, the outcome under changed future policy choices, or a successful
agent fix. Earlier E12-style affordability filtering already failed its gate.

The extended `cap_audit` accepts an optional `no_legal_action` mode. It reruns
all matching report records with invariants, requires exact record equality,
saves histories, and records the last 12 decisions with immediate alternative
successors. The default cap mode still reproduces the E16 diagnostic exactly.
Formatting, strict release workspace Clippy, and all 72 release workspace tests
pass. The history, diagnostic output, public-token feature audit, commands, and
hashes are retained in `docs/results/e18-block*` and `e18-token-audit.json`.
No agent, rule, or production source fingerprint changed.
