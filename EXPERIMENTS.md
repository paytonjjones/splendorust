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

## E19 — Preserve a legal next turn under bank depletion

**Hypothesis, before implementation:** Search can avoid the E18 block by
excluding a take when public information proves that another take preserves
a legal next turn. This is narrower than E12's affordability filter. An
affordable visible card is safe only if opponents cannot both empty the bank
and remove all affordable cards before the actor's next turn.

For a take without excess tokens and with three reservations, let B be the
remaining colored bank total and N the number of opponents. Each opponent
can take at most three colored tokens in one turn, or remove at most one
market card. Emptying the bank needs at least ceil(B/3) taking turns. Thus
the actor retains a main action if B > 3N, an own reservation is affordable,
or more than N - ceil(B/3) market cards are affordable. Payments and returns
can add colored tokens to the bank; they cannot invalidate this bound.
Apply the filter only when all root actions are takes, at least one passes
the bound, and at least one fails. Keep all takes when none passes. Apply
the same filter to zero-iteration search. Do not change heuristic rollouts,
returns, payments, core actions, or replay semantics.

Development checks: replay E18 block 818 / rotation 2 with invariants; probe
decision 83 over fixed agent seeds and hidden-world reconstructions; rerun
all 3,000 E18 screening games and compare statuses with the archived report.
These reused seeds are regression evidence, not fresh confirmation.

Use the actual promotion gate against strong, 128 iterations, depth 8,
width 6, four threads, and a 20,000-decision limit. Reserve fresh three-player
screen seed 134,000,000 (3,000 games) and confirmation seed 1,134,000,000
(21,000 games). Then check two players at 136,000,000 / 1,136,000,000
(2,000 / 20,000 games) and four players at 135,000,000 / 1,135,000,000
(4,000 / 20,000 games). Run stages in sequence without concurrent simulation
work. Any incomplete stage rejects promotion. Retain failed evidence as
well as successful evidence. These comparisons measure search against the
stated heuristic opponents, not equal-compute or universal strength.

**Development result:** The E18 regression set now completes all 3,000 games:
2,999 completed controls stay complete and the one blocked control completes.
Block 818 / rotation 2 ends after 78 turns and 116 decisions, scores 18/7/5,
winner mask 1, trajectory hash `445dbcad68d2731b`. Invariants pass. The
original blocked history stays intact as a v2 fixture with no core outcome.
Tests explore every complete opponent reply to all six blue-containing takes
at decision 83. Every branch that reaches the actor again has a legal action.
The fixed-seed probes also preserve choices across equivalent hidden worlds,
including zero-iteration and one-iteration search.

**Three-player gate:** All 3,000 fresh screen games and all 21,000 confirmation
games complete. Search wins 11,007 confirmation games, for 52.414% win credit
and 95% CI [51.162%, 53.666%]. The lower bound exceeds the 34.333% gate
threshold. The actual gate returns `promote`. A repeat after a unit-test
assertion refinement has identical ordered records for all 24,000 games.
Those repeated seeds are not additional independent confirmation evidence.
The final production fingerprint is `9a5cd6ed81093bd5`.

**Four-player gate:** All 4,000 screen games and all 20,000 confirmation games
complete. Search earns 39.145% confirmation win credit, with 95% CI
[37.813%, 40.477%]. The gate returns `promote`. This is a separate confirmation
against three strong opponents at the stated search budget.

**Two-player gate: rejected.** All 2,000 screen games complete, but two of
20,000 confirmation games block. The gate correctly rejects the incomplete
confirmation. Both blocked records, and the other seat rotation of each
setup, reproduce exactly under the saved unmodified `69232e5` release binary
with invariants enabled. The failed records are block 786 / rotation 1
(seed 6745147577365571494, hash `cfd3539f2f3c2944`) and block 6349 / rotation 0
(seed 16072322170756429076, hash `c58f9f9581a0742d`). These two failures predate
the patch. They remain unfinished with no winner and do not qualify for a
two-player promotion claim. This targeted control is not a comparison of all
20,000 candidate/control records.

Retain the fix for the reported E18 block, with successful three-player and
four-player gate evidence. Do not claim universal termination or promote the
incomplete two-player run. No core rule, RNG, enumeration, or replay behavior
changes; the engine stays v2. Compressed reports, recomputed intervals,
record-set hashes, gate decisions/manifests, control comparisons, and final
validation are retained under `docs/results/e19-*`.

## E20 — Apply next-turn safety to Strong and token returns

**Hypothesis, before implementation:** Both E19 two-player confirmation failures
block Strong (identity 1), rather than Search. A token take followed by a return
can leave Strong without an affordable card when Search empties the remaining
bank. Extend E19's public sufficient next-turn bound to Strong and to complete
return bundles. When certified alternatives exist, exclude uncertified choices.
Use only the actor's public observation and private reservations. Preserve all
core rules and legal actions; this is not a universal termination claim.

Development seeds are the two E19 blocks, 786/rotation 1 and 6349/rotation 0.
Retain their original complete histories and no-outcome endpoints. Check all
opponent replies to certified root choices, repeated choices and equivalent
hidden observations, and whole-game completion. Reserve fresh screen 138m
(2,000 games) and confirmation 1,138m (20,000 games), Search versus Strong,
128 iterations/depth 8/width 6, four threads, decision cap 20,000. Use the
promotion gate and retain failures. This gate measures the combined changed
policies against each other; it cannot isolate a strength gain for either.

**E20 initial result:** Both recorded E19 games now complete. Strong first
changes its take at decision 47 (block 786) and 31 (block 6349). Each changed
take preserves a legal next turn against every legal opponent reply. The
fresh 2,000-game screen completes. The 20,000-game confirmation has two
Strong blocks, blocks 2310 and 4285, rotation 1. The gate rejects. Preserve
this failed candidate and its full reports; do not reuse its confirmation
as a fresh holdout. Initial gate execution also stopped on Clippy diagnostics
before any seed-based stage; that execution failure is retained separately.

## E21 — Do not take the last bank tokens into a proven opponent block

**Hypothesis, before implementation:** At both E20 failures Search can buy
but takes the last colored bank tokens, leaving Strong with no legal action.
Exclude such a take when the actor can choose another action. Certify the
next actor's block only from public information: exactly three reservations,
all reservation identities known, no affordable market or reservation,
empty colored bank after the take, and no return needed by the current actor.
Do not infer blind reservation identities. This adds no core outcome or pass.
Use the same check for Search and Strong. Keep all actions if every action
would fail the check. Combine it with the E20 own-turn bound. Reserve fresh
screen 140m / confirmation 1,140m, 2,000 / 20,000 two-player games at 128/8/6.

**E21 policy boundary:** This changes Search root/non-main decisions and real
Strong decisions. Search's internal Strong rollout still uses the existing
`best` scoring directly. No rollout budget or rollout policy changes.

**Fresh two-player gate:** All 2,000 screen games and all 20,000 confirmation
games complete. Search earns 72.9325% win credit with 95% setup-block interval
[71.8544%, 74.0106%]. The actual gate returns `promote` at source
`bc768d0c493a603f`. This measures the changed policies against each other;
it is not evidence that the safety filter increases either policy's strength.

**Fresh three-player gate:** All 3,000 screen games and all 21,000 confirmation
games complete. Search earns 52.4714% credit, with 95% interval
[51.2257%, 53.7171%], against two changed Strong opponents. The gate returns
`promote`. These gates do not prove full-game termination for other seeds,
search budgets, policies, or player counts.

**Fresh four-player gate:** All 4,000 screen games and all 20,000 confirmation
games complete. Search earns 39.0125% win credit, with 95% interval
[37.6787%, 40.3463%], against three changed Strong opponents. The gate returns
`promote`. The three fresh gates complete 70,000 games in total, with no
blocked or capped game. Timing is shared-machine promotion metadata; no
comparative speed claim follows. Full reports, hashes, manifests, failed
E20 evidence, and validation logs are in `docs/results/two-player-policy/`.

**Search32 self-play diagnostic:** A separate 300-game invariant-checked run
for each player count at seed 143m uses 32 iterations/depth 8/width 6.
Two players complete 293 games and cap seven; all seven have a verified
four-decision token-only cycle. Three and four players each complete 298 games
and block two. This self-play workload is incomplete and cannot use completed
count as if all requested games finished. The reports, all eleven unfinished
histories, and local branch audits are retained.

The three-player block 66 has an opponent blind reservation, so E21 cannot
prove the block from public information. Block 4 ends with the sole zero-token
payment after a free purchase; that path is outside the take-only guard.
Both four-player blocks end with the sole legal take. E21 correctly retains
a legal choice when no alternative exists. No guard defect is established.
Do not invent a pass or winner, or extrapolate Search/Strong completion at
128 iterations to self-play at 32. Use the completed Search/Strong workload
for the primary search benchmark and retain self-play as incomplete evidence.

## E22 — Preserve last-seat takes that end through a noble

**Hypothesis, before implementation:** E21's next-actor block proof overlooks
one normal terminal boundary. A last-seat actor with at least 12 prestige can
claim an already eligible noble after a take, reach 15, and end the game even
when `final_round` was false before the take. Multiple eligible nobles still
require exactly one choice; every choice adds three prestige. Exempt this
boundary from the next-actor guard. Preserve the guard for an earlier seat,
where the next actor must still play. Do not change core rules or noble choice.
Use invariant-valid observations and actual core transitions to test both
seat cases and multiple eligible nobles. Keep the E21 70,000-game evidence
under its original source identity; check whether the narrow change alters
those ordered records before reusing their completion claim.

**E22 result:** The new invariant-valid unit regression passes for both seats
and single/multiple noble choices. All 82 release Rust tests, strict release
workspace/all-target Clippy, and all 57 Python tests with the pinned external
reference pass. The initial constructed test fixture had incorrect seat/turn
parity; that fixture was corrected before simulation reruns.

Reran the exact E21 screen and confirmation schedules for all three player
counts at corrected source `d059908db50b9d49`. All 70,000 ordered game records,
including statuses and trajectory hashes, are identical to E21 source
`bc768d0c493a603f`; every game completes. These are reused-seed equivalence
checks, not fresh playing-strength evidence. E21 archives remain unchanged.
The raw reruns, gate/build manifests, paired record hashes and check logs are
retained in `docs/results/noble-boundary/`. No performance claim is made.

## E23 — Observation-only learned leaf value

Hypothesis before implementation: a small logistic outcome model using public
engine progress and card affordability can improve root search at 128 simulations.
Freeze Search at commit 4448c19. Keep its selection and leaf evaluation unchanged.
First use completed Strong self-play outcomes; record and exclude incomplete
labels explicitly, without assigning outcomes. Split by setup seed. Training:
210000000; development: 220000000. Internal screens start at 230000000.
Reserve 1230000000 for confirmation; do not read it during development.
Use a linear model first to bound inference cost. Candidate features must come
only from Observation. Keep the core unchanged. Outcome prediction quality is
not a promotion criterion. Use the existing promotion gate for retained changes.

**E23 first result:** Strong self-play generated 570,406 training positions from
20,000 setups and 114,012 development positions from 4,000 distinct setups. All
games completed. Development Brier loss is 0.20296 versus 0.23420 for the old
engine leaf and 0.25 for constant 0.5. This is outcome prediction, not strength.
The 2,000-game screen at 232m completed 1,981 games and capped 19. Conditional
win credit is 78.12%; conservative 95% bounds including missing outcomes are
[73.58%, 82.05%]. Reject promotion because the run is incomplete. Preserve the
checkpoint and reports. The 200-game smoke cap is a verified four-decision
token cycle: the learned actor has five legal purchases but repeatedly takes.
This resembles the documented rollout/real-policy mismatch in E11/E16.
Search's 2,000 baseline records match the frozen executable exactly.

## E24 — Learned value with observed-cycle escape

Hypothesis before implementation: E23's strength gain can survive a narrow
observation-history purchase fallback that prevents its repeated token cycles.
Keep the E23 checkpoint fixed. Store the last 16 Main observations, ignoring
only completed-turn count. If the same observation returns and purchases exist,
search among the legal purchases. No inferred hidden state, core rule, or
outcome changes. Unlike E11, test this with the learned evaluator. First repeat
the E23 development screen to diagnose completion changes. Then run the actual
promotion gate at fresh seed 234m, with confirmation at 1234m. Confirmation
remains unused unless the screen qualifies. Do not change frozen Search128.

**E24 result: strength gain, promotion rejected.** All 2,000 reused E23
setups complete with 78.125% candidate credit. The fresh gate screen at 234m
also completes all 2,000 games, earning 78.65%. The reserved 20,000-game
confirmation at 1234m completes 19,999 games. Conditional credit is 79.304%;
conservative bounds including the missing outcome are [78.333%, 80.272%].
Runtime is 203.13 seconds with four threads. The gate rejects the incomplete
confirmation. Keep this candidate experimental, not a promoted default. Do not
tune it from the confirmation positions. The source is c27623ac64a24f4a; raw
reports, tool hashes, build identity and rejection are in research/e24-gate.
This is strong internal evidence, but does not establish best-in-class play.
Run the frozen external two-player schedule as supporting evidence and measure
fixed-observation decision costs before any compute comparison.

## Revised development policy (user instruction, 2026-09-29)

Preregister before further experiments: development screens may proceed with
blocked or capped games. Keep every requested game in reports. Do not fabricate
wins, delete incomplete records, or call conditional win rate an unconditional
one. Report complete/blocked/capped counts and conservative missing-outcome
bounds. A candidate may advance when its lower conservative bound exceeds the
control, even if the strict existing promotion script rejects incompleteness.
Preserve that rejection. Final evaluation will report all missing outcomes and
will distinguish measured strength from the strict completion gate. This rule
applies prospectively; E23/E24 gate records stay unchanged. Do not tune on final
confirmation seeds or individual confirmation positions.

## E25 — Residual neural policy/value and information-set PUCT

Hypothesis before implementation: a nonlinear observation encoder with shared
policy/value representation, trained from E24 self-play, will improve planning
beyond the linear leaf. Use a residual MLP with 128-wide hidden layers, a
67-action main-policy head and a scalar outcome head. Train with masked policy
cross entropy and outcome value loss. Policy targets are teacher choices;
record this as distillation, not AlphaZero visit-target self-play. Keep setup
splits independent. Generate 12,000 training games at 250m, 2,000 development
games at 260m, with independent policy streams 950000007/960000007. Use the
E24 learned-cycle teacher at 128 simulations. Incomplete games retain policy
labels but no value labels. Use 2,000-decision data caps and no invented winner.

Runtime is native Rust float32 inference; PyTorch/MPS training is isolated in
the research environment. Encode relative player state, known reservations,
market cards, bank, remaining deck sizes, nobles and final-round state. Never
encode actual future decks, opponent blind card IDs or setup RNG state. Test
Rust/Python inference parity. Then use observation-keyed PUCT with fresh root
hidden-world sampling and explicit real outcomes. Keep all core rules intact.
Development screening seeds start at 270m; reserve 1270m for final confirmation.
Do not open those confirmation positions during development.

**E25 initial result:** 12,000 teacher games yield 395,371 positions, with two
blocked games retaining masked value labels. Development has 2,000 complete
games and 65,824 positions. The 79,044-parameter residual network is trained
for 20 epochs on MPS; choose the minimum development policy+value loss only.
Rust/PyTorch maximum absolute inference difference is 0.000002862 on 16 saved
observations. The 200-game PUCT128/depth16 screen at 270m completes, but wins
only 34.5% against Search128. Do not advance this candidate to confirmation.
Before scaling, isolate failure sources: same neural priors with the E23
logistic value; old flat search with the neural leaf; neural policy without
search. Use the same development setup schedule, retaining every outcome.

**E25 component checks:** On the same 200 development games, PUCT with neural
priors and the old logistic leaf earns 38.25%; flat search with the neural leaf
gets 57.5%; the neural policy alone gets 13.82% on 199 completed games (one cap).
All intervals are wide. These checks do not isolate a confirmed population
ranking, but show that replacing the leaf alone does not recover E24's strength.
Shallow tree leaves and weak distilled priors both warrant better training.

## E26 — Search-value distillation and residual correction

Hypothesis before implementation: outcome-only supervision is too noisy for
short-horizon tree leaves, and a global dense encoder learns affordability
slowly. Add the 32 explicit E23 relative progress/affordability features to the
290 raw features. Keep the 128-wide residual network and predict a correction
to the E23 logistic logit. Train policy targets from the teacher's sampled
root-action means, softmax temperature 0.1, rather than only its selected action.
Train value against a 50/50 mixture of teacher root value and actual outcome;
for incomplete games, use only the observation-level teacher value. This is
teacher distillation, not a fabricated game outcome. Preserve the missing
outcome mask and count. Use independent training seeds 280m and development
290m, policy streams 980000007/990000007, 12,000/2,000 games. Reserve internal
confirmation seed 1300m; development screens start at 300m. Keep E25 failures.

**E26 first screens:** Both 200-game runs at 300m complete. Neural PUCT128 at
maximum depth 16 earns 41.0% against learned128; the enhanced neural leaf in
flat Search128 earns 42.5%. Neither establishes an improvement. Inference
parity maximum error is 0.000001908. Preserve both failures and do not use the
reserved 1300m confirmation. Next distinguish insufficient tree budget from
short-horizon leaf mismatch: PUCT1024, and PUCT128 with eight Strong rollout
turns at new leaves, with neural versus logistic leaf evaluation. Keep model
weights fixed. These development tests may have unequal compute; report it.

**E26 budget/rollout checks:** PUCT1024 wins 57.0% against learned128 on 200
complete development games, versus 41.0% at 128 simulations. PUCT128 with eight
Strong rollout turns gets 53.75% using the enhanced neural leaf and 51.0% using
the old logistic leaf. No small-screen result is a promotion. Native matrix
products were changed to eight independent float32 accumulators. On 20,000
inferences, median runtime fell from 0.4575s to 0.1044s. Maximum PyTorch parity
error remains 0.000003815. Floating-point summation order changed, so rerun
playing screens under the new source instead of assuming trajectory identity.
Advance PUCT1024 and rollout128 to fresh 2,000-game development screens at 301m.

**E24 frozen external result:** The unchanged 400-game two-player AlphaZero
schedule completes 212 games and marks 188 unsupported. E24 wins eight complete
games (3.774% conditional), with finite-schedule credit bounds [2%,49%] and
paired bootstrap missing envelope [0.75%,54.25%]. This is not a demonstrated
external improvement over Search's six wins in 211 complete games. AlphaZero
parameters and checkpoint are unchanged. Policy timing includes IPC and shared
host work; it is not a dedicated fixed-compute comparison. Keep the full raw
records and unsupported distribution in research/e25/e24-alphazero-*.

## E27 — Independent external teacher data

Hypothesis before data generation: self-distillation from our weak strategic
policy preserves its blind spots. Train from the stronger frozen AlphaZero
policy on NEW setups, not the benchmark's screen or confirmation schedules.
Generate 400 training games at setup seed 500m and 100 development games at
600m, with separate policy/sampling streams 700000003/800000003 and
710000003/810000003. Preserve all valid policy decisions before an unsupported
endpoint; give no outcome label to an unfinished game. Use only redacted acting
observations as inputs. This is research data generation, not an external
ranking or a new claim that the adapters implement identical games. Do not
alter AlphaZero to improve the result. Frozen benchmark holdouts remain excluded.

**E26 larger screens:** Under the faster matrix kernel, PUCT1024 completes all
2,000 games at 301m and earns 57.975% against learned128, CI [53.60%,62.35%].
PUCT128 with eight Strong rollout turns completes all 2,000 and earns 59.325%,
CI [55.01%,63.64%], at much lower cost (59.77s versus 279.34s). Select the
rollout candidate for fresh confirmation; this is not an equal-compute gain.
Reserve gate screen 302m / confirmation 1302m, 2,000 / 20,000 games against
learned128, 128 simulations, depth cap 16. Reserve 1303m separately for a
20,000-game final comparison against original Search128. Do not tune using
these confirmation positions. The earlier reserved 1300m remains untouched.
A profile shows substantial debug-string allocation/hashing in tree lookup.
Replace keys with fixed bytes containing every Main observation field except
turn count, and require exact record equivalence before using the new build.

**E27 data:** Training has 400 games, 227 complete and 173 unsupported; the
17,033 redacted main positions include 8,479 expert policy labels. Both actors
can provide value labels from the 227 verified terminal histories (12,074 rows).
Opponent policy rows have zero policy weight. Development has 100 independent
games, 56 complete, and 4,296 positions. Preregister 30 fine-tuning epochs from
the E26 checkpoint, learning rate 0.0003, 50% expert rows and 50% E26 replay
rows per epoch. Missing expert outcomes have no value loss; do not replace
these with teacher estimates. Select by independent development policy plus
value loss. This is fine-tuning, not learning from evaluation holdouts.

**Compact-key check:** All 2,000 ordered E26 rollout-screen records match after
replacing debug-string keys with fixed observation bytes. Shared-host runtime
is 42.81s versus 59.77s; this is a single equivalence/timing pair, not a precise
hardware speed claim. The fresh E26 gate screen at 302m completes all 2,000
and earns 56.125%, CI [51.79%,60.46%]. Confirmation is now running unchanged.
E27 will first use a 200-game development screen at 310m against neural-rollout,
with both policies using 128 simulations, depth 16 and eight Strong rollout
turns. Reserve 1310m for a future final confirmation if development qualifies.

**E26 confirmation:** All 20,000 games at 1302m completed. Candidate credit is
57.725%, with block-based 95% CI [56.5925%,58.8575%]. The unchanged strict
promotion gate returned `promote`; source 7089d131c74a3c28 and all hashes are
in research/e26-gate/decision.json. This supports an internal gain at 128
simulations, not equal compute or external leadership. Run the previously
reserved 1303m comparison against original Search128 and the unchanged external
400-game AlphaZero schedule at 2051000. Do not use these histories to tune.

**E27 result:** Independent expert development selected epoch 3; later epochs
overfit. Development policy accuracy is 34.33%, value Brier 0.11671, and native
inference parity error is below 0.000002504. However, the fresh 200-game playing
screen at 310m earns only 38.75% against neural-rollout (all complete). Reject
this candidate for promotion. Preserve the checkpoint, raw teacher histories,
training curves and playing result. A better held-out prediction loss alone is
not sufficient evidence of a stronger search policy. Seed 1310m remains unused.

**E26 fixed-time protocol, before measurements:** Compare the selected E26
rollout agent with the original Search algorithm at one millisecond of search
loop time per Main decision, a ceiling of 100,000 simulations, and one arena
thread. Search retains depth eight, width six and Strong/Engine evaluation;
E26 retains depth sixteen and its frozen weights. Both existing implementations
check the clock between simulations, so one simulation can exceed the budget.
Preparation and final choice are outside that loop budget. Report actual total
runtime as well; this is a matched search-time comparison, not a hard latency
limit or a bitwise reproducible run. Use 2,000 development games at 320m and
reserve 20,000 independent confirmation games at 1320m. Keep all incompletes
and report their bounds. The named Search128 control remains unchanged.

## E28 — Search policy iteration from the confirmed neural agent

Hypothesis before implementation: E26 can improve its own strategic prior by
distilling a higher-budget version of its full tree search, rather than the
old root-only teacher. Expose normalized root visit counts and the selected
edge's mean value without changing action selection. Generate 6,000 training
games at master 340m and 1,000 development games at 350m, with independent policy
streams 1040000007 and 1050000007. Use frozen E26, 256 simulations, depth sixteen,
and eight heuristic rollout turns. This is deterministic search policy
iteration; no claim of exploration-noise AlphaZero training is made.

Warm-start E26 for 30 epochs at learning rate 0.0003, with equal sampled weight
on new data and the original E26 replay. Use the existing mixed-replay trainer,
which masks missing outcomes and retains observation-only teacher values.
Select by independent development policy plus value loss. First screen is
200 games at 360m against E26 at 128 simulations/depth sixteen; only advance
on playing evidence. Reserve 1360m for later confirmation. No external or
internal confirmation histories are training inputs.

**E28 target validation:** All 2,000 ordered E26 development game records are
identical after adding root training targets. The hidden-world test also checks
identical targets, legal policy support, normalized visit probabilities and
bounded values. Target collection does not change the policy's choices.

**E26 fixed-time screen:** 1,999 of 2,000 games completed at 320m. The candidate
earned approximately 76.01% conditional credit. Keep the one missing outcome
in the unconditional interval. As preregistered, advance to the independent
20,000-game 1320m confirmation. Runtime budgets are nondeterministic and this
is not eligible for the deterministic strict promotion gate. This shared-host
run overlaps other research jobs; both actors use the same per-decision clock
budget, but this is not a dedicated-hardware latency claim.

## E29 — Reuse observation-matched search nodes

Hypothesis before implementation: keeping exact observation-matched nodes
between real decisions can recover useful prior search work at low cost.
Use the frozen E26 model and search settings. Retain at most 32,768 nodes
between decisions; clear the cache at the next decision when above that limit.
Require an exact observation key match, preserve legal root action restrictions,
and continue fresh hidden-world sampling for every new simulation. The key
excludes only turn count, as in the already-validated within-decision tree.

This reuses finite-horizon estimates from different root depths, which can
introduce bias. Measure actual play rather than assume benefit. Screen 200
games at 380m against fresh-tree E26, with both at 128 simulations/depth sixteen.
Reserve 1380m for confirmation only if development qualifies. This independent
search experiment does not alter the frozen E28 data-generation process.

**E29 screen result:** All 200 games completed. Persistent search earned
49.75% against the fresh tree, CI [29.53%,69.97%]. No benefit is demonstrated;
do not advance to confirmation or replace the selected E26 agent. Preserve
this implementation as an experimental ablation and its raw failure evidence.
Seed 1380m remains unused.

**E26 versus original Search128 confirmation:** The reserved 1303m run finished
19,999 of 20,000 games, with one incomplete game. Candidate credit among complete
games is 83.00%; the all-requested 95% interval is [82.09%,83.91%]. The strict
report gate rejects the incomplete game. Under the user-approved development
rule, this is strong evidence of internal improvement with the missing outcome
retained in the bounds. It does not establish an external ranking.

**E29 regression:** The fresh-tree path retains all 2,000 ordered E26 development
records exactly. Rust formatting, strict Clippy and release workspace tests
pass with the cache ablation and its hidden-world/legality test.

**E23 reproducibility audit:** Current value_data with independent policy seed
arguments reproduces both original Strong-generated files byte for byte.
The train/dev hashes match the model manifest; the policy-seed refactor did not
change these deterministic Strong trajectories. Retain the original manifests
and separate reproduced manifests rather than rewrite historical evidence.

**E26 fixed-time confirmation:** All 20,000 games at reserved 1320m completed.
Neural rollout earns 76.6175% against the original search algorithm under the
matched one-millisecond search-loop allowance, 95% CI [75.60%,77.63%]. This
confirms a gain under the stated shared-host timing protocol; it is not a
bitwise-reproducible promotion. Actual total runtime was 1182.03 seconds.

**E26 external confirmation:** Frozen AlphaZero800 wins decisively. E26 earns
14 wins in 240 completed games, with 160 unsupported of the requested 400.
All-requested finite-schedule bounds are [3.5%,43.5%], and the paired bootstrap
missing envelope is [1.75%,48.5%]. Preserve all 160 incomplete records. Even
assigning them all to E26 does not produce a winning finite-schedule score.
There is no best-in-class claim.

**E28 data and first result:** All 6,000 train and 1,000 development games
completed, with 167,616 and 27,934 positions. Training selected its checkpoint
using only development prediction loss. Rust parity error is 0.000002862.
The fresh 200-game 360m screen earns 58.25% against E26, all complete. Extend
the same development schedule to the standard 2,000-game gate; this extension
is not a fresh holdout. If it passes, use the already reserved independent
1360m confirmation of 20,000 games. The checkpoint stays fixed.

Train and development generator manifests have different source fingerprints
because the unused E29 ablation was added between process launches. E26's
weights, settings and action records remain fixed. The first 128 setups from
each dataset reproduce byte for byte with the saved generator binary, including
all policy/value labels. Retain both fingerprints and the prefix checks.
The setup audit reports zero intersections among all recorded train, development
and completed final-report schedules.

## E30 — Transfer the stronger pretrained network into native inference

Hypothesis before implementation: the remaining external gap is largely a
learned-policy gap. Test transfer of the frozen external version-80 network
itself, with explicit attribution, rather than distilling only a few hundred
of its decisions. First export and verify native Rust inference against its
exact PyTorch checkpoint. This is reuse of an existing MIT-licensed model,
not an original trained-from-scratch achievement. Preserve the upstream license
and checkpoint hash. Do not change the external benchmark target.

A later playing integration must receive Observation only, sample hidden cards
from that observation, translate only legal core actions, and keep terminal
outcomes in the published core rules. No real future deck or hidden reservation
may reach inference. Initial parity fixtures use fresh artificial/initial board
inputs, never benchmark confirmation positions. Do not make a playing-strength
claim from inference parity alone.

**E28 confirmation and research selection:** The existing gate advances an
inconclusive non-regressing screen to confirmation; it does not require the
screen to meet the final promotion threshold. It therefore ran the reserved
1360m schedule unchanged. E28 earned 54.1677% in 19,999 complete games out of
20,000, with conservative all-requested 95% interval [53.0486%,55.2863%].
The strict decision is `reject: incomplete games` and remains intact. Under
the user's preregistered incomplete-game rule, this establishes a further
internal gain, so E28 becomes the research candidate; E26 remains the last
strictly promoted control. Rerun the unchanged 400-game external schedule.
Do not train on this confirmation history or reinterpret its missing outcome.

**E30 parity and playing protocol:** Native encoding matches upstream exactly
on 94 fresh game positions, including sampled opponent blind reservations and
equal-observation hidden-world checks. On these valid game inputs, maximum raw
logit error is 0.000006676 and maximum policy/value error is 0.000001163. The
first absolute-logit stress check failed on artificial invalid boards (logits
over 500, error about 0.002). Preserve that failure. A scale-aware stress check
and 50 legal-mask patterns per input bound normalized policy/value error below
0.001; valid-game parity remains subject to the tighter 0.0001 criterion.
The card-group mapping is semantic; upstream deck group order differs from
bonus-color order, and the export verifies all 90 cards before emitting data.

First playing screens: 200 paired games at fresh 620m against E28, for direct
transferred policy, PUCT128 without rollout, and PUCT128 with eight Strong
rollout turns. Use depth sixteen. External target stays unchanged. The network
is trained with a native 124-turn cap. For turns >=124, use Strong for real
actions and the E23 logistic value for search leaves; do not cap the real game
or invent a result. Sample all unknown reservations from the Observation only.
Reserve 1620m for a later confirmation if screens qualify.

**E30 preliminary screens:** Direct policy earns 19.25%, tree128 earns 50%,
and tree128 with eight Strong rollout turns earns 64.75%, all 200-game runs
complete. These are small screens, not promotions. A key audit found that E26
can omit turn count because its features omit it, but the transferred network
includes that field. Correct transfer-only keys to include the turn count
before further evaluation; preserve these initial screens as preliminary.
Advance the corrected rollout candidate to fresh 2,000-game development at
621m, against E28 with both 128 simulations/depth sixteen. Compute differs.

## E31 — Scale exploration to the transferred value range

Hypothesis before implementation: E30 inherited E26's exploration coefficient
1.5, while the source network was trained with cpuct 0.8 on values in [-1,1].
For our [0,1] values, its corresponding coefficient is 0.4 and its positive
first-play reduction 0.0593 becomes 0.02965. The upstream prior has no two-percent
uniform mixture. Test these three settings together as one source-informed
configuration, keeping the E30 network and legal published transitions fixed.
This is not a claim to reproduce upstream MCTS; our information-set tree and
rollouts still differ. Test tree and eight-turn rollout versions on fresh 200
games at 622m against E28, 128 simulations/depth sixteen. No confirmation until
a larger independent development screen qualifies.

**E31 first screens:** Source-scaled tree128 earns 71.75% against E28 on 200
complete games at 622m; the rollout variant earns 67.5%, also all complete.
Advance the faster tree variant to 2,000 fresh development games at 623m and
the standard 20-game external screen at 1951000. These are selection screens,
not final confirmations. Reserve 1623m for subsequent internal confirmation.

**E28 external result:** 233 of 400 games complete; E28 earns 19.5 credits
(8.3691% conditional). The 167 unsupported games remain unknown, giving
all-requested bounds [4.875%,46.625%] and bootstrap envelope [2.875%,51.75%].
The external gap remains large. E31's small external screen at 128 simulations
earns one win in 13 completed games, seven unsupported. Do not promote on it.

## E32 — Transferred-search budget diagnostic

Hypothesis before measurement: transfer128 remains below the external target
because it has only one sixth of the target's 800 simulations. Run the same
20-game external development schedule with transfer-native at 800 simulations,
depth sixteen, while leaving the target at its frozen 800 simulations. Equal
simulation counts still do not imply equal compute. This is a budget diagnostic,
not a final ranking. Preserve all unsupported results.

## E33 — Update first-play estimates from search returns

Hypothesis before implementation: the source MCTS updates its parent Qs using
every returned value, while E31 keeps the initial network estimate fixed for
unvisited actions. With imperfect values, a fixed estimate can waste exploration
or suppress useful alternatives. Add an opt-in running mean with one initial
network-value pseudocount, matching the source Qs update formula, while retaining
E31's value scale and exploration settings. Test transfer-dynamic against
transfer-native directly on 200 fresh games at 624m, 128 simulations/depth
sixteen. All other agents retain the existing fixed estimate.

**E30/E31 larger screens:** E30 rollout128 earns 67.23% against E28 in 1,999
complete games out of 2,000 (one incomplete, conservative interval
[62.78%,71.67%]). E31 tree128 earns 68.80% in all 2,000 games, interval
[64.48%,73.12%], with lower runtime (260.07s versus 469.55s). Select the E31
search configuration for further research; final confirmation remains unused.

## E34 — Bounded root world sampling

Hypothesis before implementation: fresh worlds every simulation cause chance
branches to consume too much of the small search budget. Compare a pool of
three root worlds, sampled only from the current Observation and refreshed
every real decision, with E31's fresh-world-per-simulation control. Cycle evenly
through the three sampled worlds. Keep E31's fixed first-play estimate, cpuct
0.4, reduction 0.02965, zero uniform mixture, depth sixteen and 128 simulations.
This approximates the belief distribution and may introduce bias; it is not
access to the real deck or an exact reproduction of upstream random universes.
Test transfer-pool3 directly against transfer-native on 200 fresh games at 626m.

## E35 — Native transfer kernel optimization

Hypothesis before implementation: the profile is dominated by Norm and Dense
inference. Replace per-element modulo/index arithmetic with fixed-size array
chunks while retaining each accumulator's operation order and fused multiply
adds. Require exact saved-output equality and ordered playing-record equality
against the current build, plus upstream parity. Benchmark 30,000 calls on the
same 94 valid inputs before and after, with no other research jobs running.
The baseline median for 10,000 calls is 1.18426 seconds. This is an inference
optimization, not a new trained model or a playing-strength promotion.

**E35 result:** Median 10,000-call inference time fell from 1.184256s to
0.506491s (2.34x). All 94 saved output arrays are exactly equal
and all 200 ordered playing records match. Upstream parity remains within the
valid-input tolerance. Use this source for subsequent experiments.

**E33/E34 screens:** Dynamic first-play updates earn 46.5% against E31 on
200 complete games; no benefit shown, do not advance. Three sampled root worlds
earn 63.25% against E31 on 200 complete games. Advance only this sampling variant
to 2,000 fresh development games at 627m. E32's 800-simulation external screen
earns three wins in 12 completed games, with eight unsupported. Budget helps
but does not close the gap in this small screen. Test the three-world variant
at the same 800-simulation external development budget as a separate diagnostic.

**E34 larger result:** All 2,000 fresh development games at 627m completed.
Three-world search earns 62.525% against E31, conservative 95% CI
[58.37%,66.68%]. Its external 800-simulation development screen earns 7.5
credits in 14 completed games (53.57% conditional), with six unsupported.
This is promising but too small for a final external claim. Preserve all
missing outcomes. The next final candidate assessment will use the unchanged
400-game external schedule and a fresh internal promotion gate.

## E36 — Final assessment of the three-world candidate

The completed development evidence selects transfer-pool3. Freeze the E30
checkpoint, cpuct 0.4, first-play reduction 0.02965, zero uniform mixture, three
fresh root worlds per real decision, depth sixteen and the E35 inference kernel.
Run the existing strict promotion script against E28 at 128 simulations: fresh
screen 628m (2,000 games), independent confirmation 1628m (20,000 games).
Preserve strict incomplete rejection. If a published-rule gap stops the screen,
continue the reserved confirmation only as a research measurement under the
user-approved incomplete policy, with all missing outcomes bounded.

Also rerun the unchanged 400-game external schedule at 2051000, with candidate
and frozen AlphaZero target both at 800 simulations. This comparison has equal
simulation counts, not a guaranteed equal-compute workload. The candidate was
selected on development data; keep all requested records and unsupported counts.
The already-used external schedule supports comparison with earlier agents,
while any final leadership claim will need fresh external confirmation.

## E37 — Deeper planning with the bounded world pool

Hypothesis before implementation: after chance branching is reduced to three
root worlds, the depth-sixteen cap may truncate useful terminal planning at
higher simulation budgets. Compare depth 64 with depth 16 directly, both using
three worlds, the same transferred checkpoint, native-scaled exploration and
800 simulations. Use 200 fresh paired games at 640m. The `transfer-deep` alias
fixes depth 64; the control `transfer-pool3` retains the run's depth 16. This
is a separate development experiment while E36's fixed candidate confirms.
Build it in an alternate target directory to preserve E36's executable between
its screen and confirmation stages. Do not tune from E36 final histories.

**E37 result:** All 200 games completed. Depth 64 earned 51.25%, with
conservative interval [30.38%,72.12%]. No gain shown; retain depth 16 and
do not advance this variant. Raw records and validation logs are retained.

## E38 — More sampled hidden worlds

Hypothesis before implementation: the successful three-world pool reduces
chance branching but may overfit a few sampled hidden states. Test eight worlds
against three with the frozen transferred checkpoint, depth 16 and 800
simulations. Use 200 fresh paired development games at 641m. Only the world
count changes. This test does not use E36 confirmation histories. If the
screen shows no clear gain, retain three worlds.

## E39 — Total decision cost of the transferred model

Measurement hypothesis before implementation: fixed simulation counts do not
measure equal compute. Extend the fixed observation benchmark with transfer
budgets 16, 32, 64, 128, 256 and 800. Use the unchanged 568 Strong-game Main
observations and reverse the order on the second of three repetitions. Measure
all preparation and action selection, simulations and inference calls. Run
after E36 and E38 processes finish to reduce shared-host interference. Use
these costs to select a later matched-compute development budget; do not claim
strength from a latency result or tune from final game histories.

**E38 result:** All 200 games completed. Eight worlds earned 47.25%, with
conservative interval [26.89%,67.61%]. No gain shown; retain three worlds.

**E36 screen:** All 2,000 games completed. The frozen three-world candidate
at 128 simulations earned 81.55% against E28, conservative interval
[77.85%,85.25%]. The script advanced to the reserved confirmation. Do not
use that final schedule to guide the independent E37/E38 experiments.

## E40 — Reusable self-improvement loop

User direction: stop separate search ablations and focus on useful learning
iterations per wall-clock. Hypothesis before implementation: the current
three-world bootstrap search can teach a stronger native policy/value network
through repeated search distillation and self-play, without rebuilding Rust
for each checkpoint. Retain the bootstrap architecture for the first pass to
reuse its weights and fast inference. Larger architectures are allowed when
measured iteration cost supports them; no architecture is selected on loss alone.

Build a restartable sharded loop: immutable best checkpoint -> independent
self-play shards -> bounded-memory PyTorch training -> exact native export ->
PyTorch/Rust parity -> paired arena screen -> reserved confirmation -> retain
or reject. Preserve the best model on rejection. Store raw data, model hashes,
source identities, times and every stage decision. No runtime Python or core
rule changes. Checkpoint loading must occur once per process, outside search.

First generation uses 128-simulation best search, depth 16, three sampled
worlds and all Main observations below the network's turn-124 domain. For the
first six total turns, sample legal root-visit probabilities for diversity;
later choose the normal search action. Labels are full root visit targets,
root selected-edge value and actual terminal credit. Incomplete games retain
policy/value teacher supervision but mask terminal outcome. Do not invent
wins or stop the data pipeline on a blocked game. Teacher features are encoded
only from the actor Observation with a separate encoding RNG stream.

Reserve train masters 800m..800100000 (100,000 games in 1,000-game shards),
development 810m (1,000 games), first arena screen 820m (2,000 games), first
confirmation 1820m (20,000 games). Begin with five training shards to verify
one full learning cycle; expand collection after checks. Never train or tune
on confirmation histories. Future cycles receive disjoint master ranges.

E40 full run schedule: cycle 0 uses 5,000 train games at 800m; cycle 1
uses 20,000 at 900m; cycle 2 uses 75,000 at 1000m. Each cycle has 1,000
development games at train+10m, a 2,000-game screen at train+20m and a
20,000-game confirmation at screen+1b. Training includes earlier train
shards as replay. This supplies 100,000 distinct training setups while
allowing a complete small learning iteration before the largest collection.
The loop uses the best selected checkpoint as the next teacher. Selection
requires a confirmed conservative lower bound above 51%; strict incomplete
rejections remain unchanged and any allowed selection is marked research-only.

E40 wiring checks use 16-simulation miniature cycles at train masters 1200m
and 1300m with 64 training/16 dev games and 40/80 arena games. These are
workflow checks, not strength evidence. The first check caught a Clippy
item-order error; its failed gate/logs are retained. The repaired check will
verify two train/export/parity/gate cycles and unchanged incumbent retention.
Teacher rows from an unsearched forced action have a one-hot legal policy
and a missing teacher value; the real terminal label remains valid when
complete. Training uses masked policy cross-entropy plus [-1,1] value MSE
against equal outcome/teacher credit when both exist. Native eval omits
dropout. The existing inverted residual architecture retains its upstream
MIT attribution. Epoch zero competes with trained epochs on independent dev
policy CE plus four times terminal Brier; loss alone cannot promote a model.

**E36 completed:** 19,997/20,000 complete; three no-legal-action outcomes
remain unknown. Credit 80.2345%, conservative interval [79.2445%,81.2154%].
The strict decision is reject: incomplete games. Select as a research teacher
under the user-approved bounded missing-outcome policy. External: 202 complete,
198 unsupported, 93.5 credits, 46.2871% conditional; full-schedule bounds
[23.375%,72.875%]. No external leadership claim.

**E39 completed:** Three fixed workload repetitions give median total Main
decision times: original128 0.7074ms, E26 rollout128 2.3270ms, transferred128
6.8433ms. Equal simulations are not equal compute. Use these recorded costs
and new pipeline stage timings to direct throughput work.

**E40 validated and running:** Two complete miniature cycles passed native
parity and rejected their unconfirmed candidates while retaining the bootstrap.
The resume check skipped all completed data/training/gate stages. Loaded versus
embedded bootstrap weights match 32 ordered records; 1/4-thread generation
matches byte for byte. First full shard: 1,000 complete games, 56,460 rows in
106.17s. The three-cycle 100,000-game collection/training plan is active. No
full-run trained model has yet earned a promotion.

## E41 — Strength gain per complete learning iteration

User steering supersedes E40's automatic 20k/75k data schedule. The driver
was stopped after starting cycle 0's gate; its live child gate remains running.
No cycle 1 collection starts without a measured assessment. Cycle 0's screen
has 2,000/2,000 complete games and 55.05% credit, conservative interval
[50.82%,59.28%]. Confirmation remains frozen at 1820m. Data generation:
6,000 games/337,966 positions in 631.315s. Training: 92.398s. Screen: 207.124s.
Use the confirmation to assess gain, not training loss or corpus size.

Conditional next hypothesis: if cycle 0 is weak or the rate of improvement
is low, stronger search targets may yield more strength per complete iteration
than more 128-simulation games. Compare 256-simulation teacher self-play
(2,500 train + 500 dev games) and 800-simulation self-play (800 train + 160 dev)
against the existing 128 teacher (5,000 + 1,000). All begin from the same frozen
bootstrap checkpoint. This is a roughly matched search-simulation workload,
not a guaranteed equal wall-clock workload. Record actual teacher positions/sec,
training time, paired-screen/confirmation time, and bounded playing gain per hour.
Full-loop trajectories and targets may both change, which is intentional here.
Use the same architecture, optimizer, ten epochs, temperature schedule and
128-simulation evaluation to isolate teacher budget from evaluation compute.
Reserve fresh ranges: 256 arm train840m/dev850m/screen860m/confirm1860m;
800 arm train880m/dev890m/screen900m/confirm1900m. No confirmation histories
enter training or hyperparameter selection. A useful target budget can be
scaled only after measured playing gain. Preserve the stronger incumbent on
rejection. Do not infer a global Elo ranking from these paired comparisons.

E41 throughput calibration before collecting either full arm: generate the
first 64 train setups at 840m with 256 simulations and at 880m with 800,
using four threads and the unchanged bootstrap teacher. This pilot measures
cost only while cycle 0 confirms; do not train or scale either arm until its
assessment. Retain these prefixes and verify reproduction if reused. Record
concurrent confirmation activity; timings are conditional on shared host load.

E41 pilots completed: 256 simulations produced 3,608 positions in 13.677s
(263.8 positions/s); 800 produced 3,594 in 42.120s (85.3 positions/s).
Both use four threads while the four-thread cycle 0 confirmation is active.
The proposed 3,000/960 total-game arms predict about 641/632 seconds of
collection, close to E40's measured 631 seconds. This calibrates cost only;
playing gain remains the deciding measurement. Both pilot files pass the
feature/mask/target/outcome checks and are retained with hashes.

E41 held-out diagnostics: root-target policy KL falls from 0.39777 to
0.34407 after cycle 0 training. Terminal Brier falls from 0.20968 to
0.20819; search-selected value targets score 0.19806. In late positions,
search targets score 0.13452 versus trained-network 0.16064. These are
correlated position-level prediction scores, not playing-strength evidence
or proof of a unique bottleneck. A residual value/target gap remains; do
not infer that collecting more low-budget rows is necessarily the right step.

## E42 — Stronger targets from the first learned incumbent

Cycle 0 confirms 54.7102% against its teacher, 19,999/20,000 complete,
CI [53.5833%,55.8368%]. One no-legal-action game remains unknown. Keep the
strict rejection and accept the checkpoint only as the research teacher under
the existing bounded-missing rule. This proves one gain, not compounding.
End-to-end wall time is 3039.808s (50.66min), 1.974 generated games/s and
111.180 positions/s, including development, checks, training and both arena
stages. Conditional relative Elo gain is 32.827, about 38.877/hour. These are
pair-specific conversions, not global ratings.

Decision before any new full collection: do not collect the scheduled 20k/75k
low-budget games. Teacher generation and arena evaluation dominate iteration
time; the trained value still leaves a late-game gap to search. Test stronger
targets with small matched-cost corpora from the newly learned incumbent.
This also tests a second actual learning iteration. E41's bootstrap pilots
remain cost evidence; do not use them as current-incumbent training labels.

Freeze teacher/student initialization d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600
(cycle 0 epoch 9). Compare train budget256 (2,500 games) and800 (800 games).
Both use 1,000 development games at budget128, ten training epochs and
budget128 arena evaluation against that same frozen incumbent. Pilot costs
predict near 631s collection per arm. This tests budget per whole learning
iteration; trajectories and targets may both change. Actual times decide cost.

Reserve 256 arm train940m/dev950m/screen960m/confirm1960m; 800 arm
train980m/dev990m/screen1000m/confirm2000m. Screen 2,000 paired games,
then fixed 5,000 fresh confirmation games. The shorter confirmation is
preregistered to reduce the largest measured time cost; preserve the >51%
conservative lower-bound requirement and strict missing-game rejection.
Do not choose or stop from intermediate confirmation outcomes. Final model
claims still require a fresh larger evaluation. Run arms independently with
four threads each; record shared-host concurrency in the comparison. Select
on actual bounded strength gain per end-to-end wall time, not loss or row count.
If neither arm improves the incumbent, test representation/capacity or a faster
student architecture before growing the same low-budget data corpus.

**E42 completed:** Budget256 trained model: 51.89% in 5,000 complete
confirmation games, CI [49.43696%,54.34304%]. Reject: gain not confirmed.
Budget800 selected epoch zero; its native bytes equal the incumbent exactly.
The 49.02% confirmation is a stochastic self-comparison, not evidence that
an actually trained 800-target model regressed. Neither model is selected.
The common budget128 development criterion can penalize improvements toward
budget800 targets. This is a selection confound, not proof of a unique cause.
Retain all raw results and checkpoints; do not grow low-budget data blindly.

## E43 — Match checkpoint selection to the teacher policy

Hypothesis before implementation: off-policy development targets from search128
favor retaining the incumbent when training imitates search800. Reuse E42's
800-game budget800 training corpus, without confirmation positions. Generate
160 fresh budget800 development games at 1050m using the same frozen cycle0
teacher d355...600. Retrain with the same seed/ten epochs/optimizer and save
both the unchanged epoch-zero candidate and the best trained checkpoint.
Select among trained epochs by held-out policy CE plus four times Brier against
the same blended teacher/outcome value target used in training. Epoch zero is
recorded separately; the arena decides whether the trained challenger improves.
This is a target/selection alignment test, not permission to promote from loss.
Reserve screen1060m (2,000 games) and confirmation2060m (5,000 games), both
at128 simulations against the frozen cycle0 teacher. Do not reuse E42 final
results for promotion. Equal native model hashes skip an unnecessary arena
self-comparison. If this fails, test a faster student representation/capacity
before additional collection with the same teacher/architecture.

**E43 completed:** 5,000 complete confirmation games: 52.8% credit,
CI [50.37%,55.23%]. Retain incumbent: lower bound does not exceed 51%.

## E44 — Reduce inner-loop evaluation cost and measure CPU scaling

Use one fixed 2,000-game paired gate per normal learning cycle; no outcome-based
optional stopping. An inconclusive result retains the incumbent and proceeds
to the next model. Explicit larger confirmations remain available for milestone
models, external claims, or ambiguous results. Strict incomplete rejection stays;
research selection still requires conservative lower bound above 51%.
Sequential stopping is deferred until a valid confidence-sequence or alpha-spend
rule is implemented; repeated fixed 95% intervals are not a stopping rule.

Scaling hypothesis: more than four threads increases useful native generation
and evaluation throughput. Run serial 256-game jobs at 4, 8, 12, and 14 threads,
then reverse that order for a second repeat. Use incumbent d355...600, 128 search
simulations, depth16, identical seed schedules within each repeat. Verify data
bytes and ordered arena records across thread counts. Select the fastest measured
thread count; preserve raw reports and source/binary hashes. No learning claim.

**E44 completed:** Two serial repeats at identical schedules preserve self-play
bytes and ordered arena records across4/8/12/14 threads. Mean games/s:
selfplay: 4 threads 9.40, 8 threads 18.16, 12 threads 22.34, 14 threads 23.35. Best14: 2.48x versus four.
arena: 4 threads 9.61, 8 threads 18.45, 12 threads 20.76, 14 threads 24.15. Best14: 2.51x versus four.
Set the learning driver default to14 threads on this host. These are workload
measurements, not strength results; raw records and binary hashes are saved.

E44 verification: Python gate tests pass (30 run,29 optional reference tests
skipped). Native32-game screen-only run saves its screen decision and creates
no confirmation report. Format, strict workspace Clippy, and release locked
workspace tests pass through the promotion tool. Miniature training/parity
run verifies identical-checkpoint skipping. Neither smoke run claims strength.

## E45 — Faster gated residual student from saved search targets

Hypothesis before implementation: the bootstrap's convolutional inference cost
limits useful search iterations per second. A flat residual network can learn
cross-card features with fewer native operations while using more parameters.
Test a width192, three-block RMS-normalized SwiGLU student (about426k weights)
on the same392 public/sampled-observation features and81 policy/two value outputs.
Reuse E42 budget256 training and development data plus budget800 training rows;
exclude every final arena trajectory. This is a new student, not a change to
rules, information access, or tree search. Train from scratch with AdamW,
learning rate1e-3, cosine decay to1e-4,24 epochs, batch1024, fixed seed
1150000007. Select one checkpoint by development policy CE +4 blended-target
Brier; save all scores, native/PyTorch parity, weights and cost measurements.

Before strength evaluation, require finite exact-length exports and native
parity on64 held-out real observations. Compare inference and total Main
search latency against frozen incumbent d355...600 on identical inputs.
Run one fixed2,000-game gate at128 simulations, seed1160m,14 threads. Retain
incumbent unless bounded lower credit exceeds51%; preserve incomplete rejection.
A speed benefit alone does not establish a playing gain. A later matched-cost
search comparison requires a separate preregistration based on measured cost.

**E45 completed:** Native parity passes (max logit error3.58e-6). Inference
26.42us versus51.12us; full128-simulation Main decision3.60ms versus6.67ms.
The2,000-game gate completes1,999:6.4032% credit, conservative CI[3.71%,9.15%].
Reject severely weaker student. One missing outcome remains unknown. The
faster architecture is retained as a prototype, never selected as incumbent.
On64 held-out rows, teacher/student value-head MSE0.3062 and correlation0.0248;
the teacher skill was not retained. This diagnostic is not a unique causal proof.

## E46 — Preserve teacher knowledge with semantic inputs and distillation

E45 receives15 packed signed deck-availability bytes as scalar inputs. Dividing
all fields by10 gives these bytes up to12.8 magnitude, while score/token fields
are near1. The bytes encode independent availability bits, not scalar amounts.
This is a representation concern, not evidence that it alone caused the loss.

Test the same192x3 gated student with these bytes cleared and decoded into120
binary availability features (512 inputs total). Keep all information supplied
by the existing sampled Observation encoder; add no real hidden information.
Distill frozen incumbent d355...600 policy and both value heads on the saved
E42 training corpus. Loss:20% original search/outcome objective plus80% frozen
teacher policy CE/value MSE. Select one trained checkpoint by development
teacher-policy KL +4 value-head MSE. Record root-target/outcome metrics too.
This tests combined knowledge retention and representation; no isolated causal
claim. Keep185,354 training and56,040 development positions, no new training
games; AdamW1e-3,24 epochs, batch1024, seed1170000007. Save teacher/script hashes.
Require native parity and measured cost. Fixed2,000-game128-simulation gate at
1180m,14 threads, no automatic confirmation; same51% bounded threshold.

**E46 completed:** All2,000 games complete;33.375% credit, CI[29.27%,37.48%].
Reject. Native parity max logit error6.36e-6; median inference29.66us.
Distillation reduces held-out teacher value MSE to0.0281 and policy KL to0.2055,
but does not preserve playing strength. This is direct evidence that lower
held-out distillation error alone is insufficient. Keep the frozen incumbent.

## E47 — Add trainable capacity without discarding the incumbent function

E45/E46 show that a faster random-start architecture loses too much teacher
skill. Test a deeper teacher-initialized network instead. Copy frozen d355...600
and add two residual trunk blocks (three total), with new projection norm scale
and bias zero. Require exact initial policy/value equality on64 held-out inputs
and native parity before training. This preserves the learned function while
adding66,594 trainable parameters; it tests capacity without random-start loss.

Reuse the same185,354 E42 train positions. Use E43's separate budget800
8,946-position development corpus to select by policy CE +4 blended-target
Brier. No final arena positions enter training/selection. Twenty epochs,
AdamW1e-4, cosine decay to1e-5, batch1024, seed1190000007. Keep epoch zero and
allow it to win selection; if it wins, skip playing the functionally identical
candidate. Native export needs a versioned header for the new trunk depth.
Measure total decision cost as well as strength: more parameters may be too
expensive even if strength rises. Fixed2,000-game128-simulation gate,1200m,
14 threads, conservative lower bound above51%; no automatic confirmation.

**E47 handoff:** Training completed in181.49s, selected epoch13. Initial
identity check is exact on64 PyTorch inputs; native initial/trained parity
checks pass. The reserved1200m gate has not run. Do not promote from its
development scores or treat this pending experiment as a strength result.

**E47 completed:** All2,000 games complete,51.225% credit, CI[46.89%,55.56%].
Retain incumbent. Gate100.73s; model inference83.24us versus incumbent51.12us.
Added capacity does not establish a gain and costs more per inference.

## E48 — Check actual strength of the proposed search teachers

Before more collection, measure whether the current learned model becomes a
stronger player at256/800 simulations versus128. Same d355...600 weights and
same algorithm; only fixed simulation budgets differ. Add explicit named budget
profiles (flywheel-best128/256/800) so report/replay names preserve the override.
Verify actual simulations on Main observations and hidden-world invariance.
Run2,000 paired games per arm:256 screen1210m,800 screen1220m,14 threads,depth16.
No automatic confirmation or intermediate stopping. Serial arenas; any offline
GPU training that overlaps is recorded. Report strength and elapsed compute.
If neither higher-budget teacher is measurably stronger, further distillation
of these targets is not justified by current playing evidence.

## E49 — Preserve the value function while training the search policy

Hypothesis: updating the critic from noisy selected-edge/outcome labels can
offset policy improvement. Freeze first layer, trunk, and complete value head,
including normalization running statistics. Train only the incumbent's policy
head against the saved185,354 E42 root-visit targets. No tree-search change and
no new training data. Frozen values must remain bit-identical on64 held-out
inputs before/after CPU export; native parity must also pass.
Use E43 budget800 dev rows, min policy CE selection,20 epochs, AdamW1e-4,
batch1024,seed1230000007. Preserve epoch zero. Fixed2,000-game128-simulation
screen1240m,14 threads. Keep the51% conservative threshold; record collection
reuse, training and gate time. No automatic confirmation and no model selection
from loss. This is a value-retention control, not evidence of a unique cause.

**E48 completed:**256 versus128:60.20%, all2,000 complete, CI[56.02%,64.38%],
144.07s.800 versus128:70.625%, all2,000 complete, CI[66.62%,74.63%],332.49s.
These are higher-compute teacher controls, not learned-model promotions or
matched-compute improvements.256 had some offline E49 GPU training overlap;
800 did not. Named profiles and actual-budget/Observation probes are saved.
Stronger search targets are supported by playing evidence; training/transfer
remains the limiting step demonstrated by the failed student trials.

**E49 screen completed:**54.5%, all2,000 complete, CI[50.31%,58.69%],85.55s.
Retain on screen alone. Training91.13s, epoch17 selected. Native first/trunk and
value-head byte ranges are exactly unchanged; policy bytes changed. CPU values
are bit-identical on64 held-out rows and native parity passes. The signal is
promising but ambiguous around the51% promotion threshold.

Before any additional outcomes: freeze candidate cde5849353068e7b11a583a39fe38a36d8499886ed5f6ee84ec6fb55c41b9a07
and incumbent d355...600. Reserve one fresh5,000-game confirmation at2240m,
128 simulations,depth16,14 threads. Do not inspect intermediate outcomes or
extend this run based on them. Use the existing strict decision and conservative
missing-outcome bounds with51% threshold. A result is conditional on this pair
and budget; larger external/milestone claims remain separate from the hot loop.

## E50 — Matched full-network control for E49

Before E49 confirmation outcomes: train the original142,406-parameter network
with all parameters and normalization statistics trainable, using exactly
E49's warm start,185,354 training rows,8,946 development rows,seed1230000007,
20 epochs,AdamW1e-4,cosine1e-5,batch1024. Use the same dev policy CE +4 blended-
target Brier criterion. E49's Brier is constant because its critic is frozen.
This removes corpus/epoch/seed confounds from interpreting E49's mode change.
The optimizer/forward path necessarily differs in whether shared features and
critic update; no unique attribution between those subcomponents is claimed.
GPU training may overlap E49 confirmation; record that shared-host load.
Run one fresh2,000-game128-simulation gate at1250m,14 threads, after earlier
arenas finish. No automatic confirmation. Keep the same51% bounded threshold.

**E49 confirmation completed:** All5,000 complete,51.68% credit,
CI[49.258%,54.102%],427.95s. Reject the proposed gain; keep incumbent.
The earlier54.5% screen did not repeat with sufficient confidence. Confirmation
and E50 GPU training overlapped; timing is conditional on shared-host load.

**E50 completed:** All2,000 complete,50.65% credit,CI[46.39%,54.91%],104.80s.
Reject. Training382.75s with E49 arena overlap; native parity passes.
Both matched training modes fail to establish a second learning gain.

## E51 — Concentrate late-game policy targets on maximal visits

Hypothesis: soft visit labels can dilute imitation of the stronger teacher's
late-game choices. Keep E49's frozen critic and policy-head training settings,
data, seed and development split. After six total turns, replace each root
visit distribution with equal mass on actions tied for maximal visits; keep
opening distributions soft. This is a greedy-visit target, not an exact replay
of the chosen move: the teacher breaks visit ties with priors, which the stored
rows do not preserve. Do not change data, search or native inference.
Twenty epochs,AdamW1e-4,batch1024,seed1230000007. Keep epoch zero. Require target
mass/legal-mask/tie tests, exact frozen critic and native parity. Reserve one
fresh2,000-game128-simulation gate at1260m,depth16,14 threads,51% conservative
threshold. No automatic confirmation or optional stopping.

**E51 completed:** All2,000 complete,49.95% credit,CI[45.65%,54.25%],76.69s.
Reject. Training71.38s,epoch9 selected. Target semantics and native parity pass;
first/trunk146,180 bytes and value-tail136,356 bytes remain exactly unchanged.
Training plus gate takes148.07s with reused data, excluding initial collection
and validation. This target change does not establish a second learning gain.

The next substantive hypothesis is independent policy/value feature learning:
allow the policy encoder to adapt while preserving the incumbent value encoder.
E49/E51 freeze shared features; E50 changes the critic when shared features
change. Separate encoders would remove that constraint. This is a proposed
experiment, not a result or a registered run. Measure added native inference
cost and fixed-compute strength before any selection. Do not collect more of
the same corpus merely because these controls failed.

## E52 — Train independent policy features with an exact frozen critic

Integrate Agent2 production commit03326dd: channel-packed pointwise inference
preserves float accumulation order and model behavior. Keep the original path
for exact comparison. Production adds no dependencies or rules changes.
Agent2's report records60.5% self-play and65–81% arena throughput gains on this
shared Mac, with exact final data/record parity. Those timings are not portable
claims. Recheck required Rust validation after integration and publish it.

Hypothesis: shared feature updates can disturb a useful critic, while frozen
shared features can limit policy learning. Start two copies of the accepted
bootstrap model. Train the policy copy's first layer, trunk and policy head;
freeze its unused value head and the complete separate critic, including
running statistics. Use one policy encoder and one critic encoder at inference,
with no unused heads evaluated. Require exact initial function and exact final
critic state/binary payload. This tests independent feature adaptation, not a
unique explanation for earlier failures.

Reuse E42's185,354 training rows and E43's8,946 budget800 dev rows. Soft visit
labels,20 epochs,AdamW1e-4,cosine decay to1e-5,batch1024,seed1230000007. Select
minimum dev policy CE, preserve epoch zero. No new collection, no final holdout
rows in training. Export a versioned dual-bootstrap header containing two
validated bootstrap payloads. Check native/PyTorch parity and measure both
inference/decision cost. Reserve fixed2,000 paired games at1270m,128 simulations,
depth16,14 threads,51% conservative lower threshold. No automatic confirmation
or optional stopping. If fixed-budget strength clears the gate, require a
separate fixed-compute assessment before retaining the more expensive runtime.

**E52 gate completed:** All2,000 complete,51.10% credit,CI[46.92%,55.28%],
66.46s. Reject; preserve the incumbent. Training98.77s,epoch18 selected.
Critic payload is byte-identical, native parity and all required Rust checks
pass. Independent policy features alone do not establish a second learning gain.

## E53 — Train from the strongest measured teacher only

Hypothesis: mixed256/800 visit targets dilute the stronger teacher's signal.
E48 measured800-versus128 at70.625%; use only the existing44,776 E42 budget800
training rows, and keep the separate frozen-critic architecture from E52.
Same warm start,optimizer,learning rate,development split,soft targets and
seed1230000007. Use80 epochs: approximately match E52's total row visits
(3.58m versus3.71m), rather than confound teacher quality with four times fewer
optimizer steps. Selection still uses the separate8,946 budget800 dev rows and
keeps epoch zero. No new training data or search change. Reserve one fixed
2,000-game128-simulation gate at1280m,depth16,14 threads,51% conservative lower
threshold. No automatic confirmation or optional stopping. Larger model cost
still requires fixed-compute assessment if the fixed-budget screen clears.

**E53 completed:** All2,000 complete,51.55% credit,CI[47.34%,55.76%].
Reject under its registered gate. The teacher-only corpus does not establish a
gain. Do not retroactively apply a new provisional rule to this completed run.
The following direction follows the user's evaluator feedback: stop architecture
changes and directly test teacher data volume and encoding noise.

## E54 — Comparable-volume800 teacher data and a provisional lineage

Use the existing142,406-parameter bootstrap model and accepted d355...600
checkpoint. Collect5,000 training and1,000 development games at800 simulations,
14 threads,depth16. Expected training positions are comparable to E40's281,778;
record actual counts and total collection cost rather than holding teacher
compute equal. Independent setup masters1290m(train),1300m(dev),1310m(screen).
Teacher policy streams are setup master+3000m. No architecture/search change.
Use the successful cycle's10 epochs,AdamW1e-4,cosine1e-5,batch1024; training
seed1300000007. Select minimum dev policy CE+4 outcome Brier; retain epoch zero.
Record root/outcome target construction and native parity. Run one fixed2,000
paired-game128-simulation screen,14 threads,depth16. No optional stopping.

Before these outcomes, create two tracks. The champion remains d355...600;
all existing strict promotion decisions remain unchanged. A provisional lineage
can accept a screen with requested-schedule worst-case credit above50.5%
(missing outcomes contribute zero). This point rule is an exploration heuristic,
not statistical confirmation. Preserve95% intervals, raw results and the strict
scripts/promote.py decision separately. No incomplete game becomes a victory.
Positive provisional choices can seed the next training generation. After at
most three candidate generations, run an independent fixed-champion milestone
assessment before any claim of compounded gain; do not select intermediate
checkpoints from its outcomes. Reserve champion assessment seed3310m,20,000
paired games for the final lineage checkpoint after those generations. A failed
milestone leaves the champion unchanged and rejects the compounded-gain claim.

First diagnose encoding variance: same public Observation, eight independent
encoder determinizations, legal-masked policy total variation/argmax agreement,
value range/std. Separate no-blind and opponent-blind observations. The sampler
must include ordinary play and an explicit blind-reservation stress cohort;
stress frequency does not estimate ordinary-play prevalence. Keep target labels
fixed if a later multi-view training control is justified. This diagnostic
contains no final screen observations or actual hidden-card inputs.

**E54 encoding diagnostic:**896 ordinary Strong-play observations have no
opponent blind reservation; eight encodings give exactly equal inputs/outputs.
The explicit blind stress cohort has672 observations with opponent blind
reservations. Mean legal-policy TV from the eight-view mean is0.0632;
11.79% of view argmax choices differ from that mean. Mean raw value range is
0.1323 (probability range0.0661), maximum0.4087. This is substantial conditional
sensitivity, not evidence of its frequency in neural self-play.

Capture seven extra encodings only for opponent-blind rows during E54
collection. Use a separate encoder RNG so original data/search trajectories
remain unchanged. Save a sidecar with base-row indices and7x392 floats, aligned
with immutable original labels. Record actual blind-row frequency. E54 still
trains only the original view. This enables a paired input-noise control without
another expensive teacher run. Sidecars do not introduce true hidden-card data.

## E55 — Paired multi-view training control

Use the same E54 corpus, warm start,architecture,labels,optimizer,epochs,seed and
dev selection. For each training row with captured alternatives, uniformly
choose one of its eight encodings on each epoch visit. Keep original masks,
root targets and outcomes. Use a separate augmentation RNG so shard/row order
remains matched. No-blind rows stay unchanged. Development uses the original
view for checkpoint selection; separately report eight-view output sensitivity
before/after. No architecture or search change. Fixed2,000-game screen1320m.
Assess against the current provisional lineage, retain the fixed champion, and
use the same predeclared50.5% worst-case requested-schedule point rule. No
statistical promotion claim. Final lineage milestone remains the fresh3310m
20,000-game test after no more than three candidate generations.

E54 seed correction before training or screen outcomes: the existing driver
uses training seed800000007 for cycle0. Use that successful-cycle seed, replacing
the earlier1300000007 entry. E55 uses the same800000007. All data/screen masters
and other settings remain unchanged. The immutable run plan records this driver.

**E54 teacher-observation diagnostic:** First1,000 completed800-simulation games
contain56,280 rows;10,412 (18.50%) have an opponent blind reservation. One
random blind observation from each of512 sampled games has mean eight-view
policy TV0.0503,argmax disagreement8.45%,and mean raw value range0.2298
(probability range0.1149). This supports the paired multi-view control on actual
teacher inputs. It does not prove that encoding noise causes playing failures.

## E56 — Third candidate generation from the provisional teacher

After E54/E55 complete, freeze the resulting lineage checkpoint. Collect1,000
fresh train games at1390m and1,000 fresh dev games at1400m,800 simulations,
14 threads,depth16,with extra encoding views. Train from that lineage with
E54's5,000 original train games replayed alongside the1,000 fresh games.
Keep architecture,loss,epochs10,learning rate1e-4 and batch1024. Seed800000008.
Use multi-view sampling only if E55 advances the lineage; otherwise use original
inputs. Select on the fresh dev corpus using policy CE+4 outcome Brier. Keep
epoch zero. Fixed2,000-game128-simulation screen1410m against the parent lineage,
same provisional50.5% requested-credit point rule. This is the third candidate
attempt; no extra candidate selection from the milestone outcome.

Freeze the resulting endpoint and assess against d355...600 at3310m,20,000
paired games,128 simulations,depth16,14 threads,using scripts/promote.py.
Keep its strict decision and conservative intervals. If endpoint weights equal
the champion, skip the self-comparison and record no learning gain. A provisional
path with a failed final assessment does not establish compounded improvement.

**E54 screen completed:** All2,000 complete,56.775% credit,CI[52.514%,61.036%].
Strict screen promotes; provisional lineage also advances. Native SHA1264435767ffe18cee9b195bc0aaa54c568d92844ceffc8a73c3c8b950a356be.
Architecture remains142,406-parameter bootstrap; epoch10 selected. Train corpus
has281,432 rows from5,000 complete games, comparable to the successful cycle.
Dev has999 complete games and one blocked game;37 unknown outcome rows remain
masked while legitimate teacher targets can still be used. This is a screen
result, not the independent lineage milestone. Keep d355...600 as fixed champion.
The full-volume control supports stronger-teacher data as a useful direction;
it does not isolate teacher volume from every data-distribution difference.

## E57 — Frozen-endpoint controls and external supporting rerun

After E56 freezes its endpoint, assess it against frozen search128 at128 and
16 NN simulations (2,000 paired games each,3420m and3430m),and against Strong
at128 (2,000 games,3440m). Keep actual named search128 override128/depth8;
NN uses depth16. Measure fixed-observation decision costs for search128 and
NN16/128 with the same endpoint. The16 budget is chosen before outcomes from
prior timing evidence; report measured cost, not exact universal compute parity.
Native controls remain distinct from external rankings.

Rerun the frozen AlphaZero profile with400 games,two-player seat rotations,
setup master3450000,policy2500001,sampling3500001,native800/depth16,external
iterations0 (unchanged checkpoint default),cap2000. Keep AlphaZero source,
checkpoint,adapter and all benchmark parameters unchanged from E36 except the
candidate weights/name and fresh setup master. Add only the native candidate
name to the harness whitelist and model-hash provenance. Keep unsupported,
blocked and capped outcomes unknown. Do not infer a global/SOTA rank from
conditional completed-game credit. Native controls and external process may
overlap the fixed-budget milestone; record shared-host timing interference.

**E55 completed:** All2,000 complete,49.525% versus E54,CI[45.26%,53.79%].
Reject by the predeclared provisional rule; retain E54. Training96.17s,gate48.73s.
On512 development blind observations,mean policy TV is0.04675 for E54 and
0.04650 for E55; raw value range0.22534 versus0.22447. This particular random-
view control makes little difference to measured sensitivity and establishes
no playing gain. It does not rule out other observation-level learning methods.

**E56 screen completed:** All2,000 complete,51.15% versus E54,
CI[47.01%,55.29%]. The strict gate retains E54; the registered provisional
lineage advances to055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41.
This small screen gain is unconfirmed. Freeze this endpoint before the reserved
20,000-game3310m champion milestone. E56 used original inputs because E55 did
not advance. No further candidate selection from milestone outcomes.

E57's first native control writes all2,000 records, including four incomplete
ones, then the CLI returns1. The first runner incorrectly expected exit2 for
incomplete CLI comparisons. Preserve its source/plan/log, repair the runner to
validate complete record sets on exit1, and continue the other registered
controls. Keep the existing external process; no schedule restart or dropped
unknown outcomes. This is execution handling, not a new experiment or result.

**E56 milestone completed:** Frozen055c42...f41 scores55.26% against fixed
d355...600 at128 simulations,20,000/20,000 complete games. Independent95%
interval54.1349–56.3851%; strict promote. This establishes a second learning
gain; the small E56-over-E54 screen difference remains separately unconfirmed.
`research/CHAMPION.json` now points to E56. Raw record SHA6923f6...8de.

**E57 completed:** NN128/Search12895.641% (1,996 complete,4unknown),
NN16/Search12882.882% (1,995 complete,5unknown),NN128/Strong97.625%
(2,000 complete). Fixed568-observation medians0.835ms/1.137ms/6.265ms
for NN16/Search128/NN128 under shared CPU load. AlphaZero209/400 complete,
191unsupported;59.809% conditional credit. Requested bounds31.25–79%,
paired bootstrap missing envelope26.625–83%. No external rank. All400
histories replay correctly; external policy configuration equals E36.

## E58 — Full-volume next teacher generation

Hypothesis: E54 showed that 5,000 games from an 800-simulation teacher can
teach a stronger 128-simulation model. Repeat that volume with the confirmed
E56 teacher. Keep its recent 1,000-game predecessor replay shard. Collect
5,000 fresh train games (master 3510000000) and 1,000 dev games (3520000000),
with 800 simulations, depth 16, and 14 threads. Add E56's 1,000 training games
as replay. Keep the 142,406-parameter bootstrap architecture, original inputs,
loss, and 10 epochs. Use batch 1024, learning rate 1e-4, and MPS. Warmstart
E56 with training seed 800000009. Select epoch 0..10 using dev policy CE plus
4 times outcome Brier. Do not select a model with arena outcomes. Use a fixed
2,000-game paired screen at 3530000000, 128 simulations, depth 16, and 14
threads against E56. Apply the registered provisional requested-credit point
rule (>50.5%). Keep the strict decision and 95% interval. Do not use a 20,000-
game confirmation in this inner loop. Unknown outcomes stay unknown.

**Strategy update:** Use the smallest experiment that answers a question. This
is not a constraint on the resulting design. After each teacher campaign,
reassess strength gain per total wall time and the remaining teacher–student
gap. If data and optimization controls show a structural limit, pursue a
larger architecture, search, or training change. Do not continue small tweaks
solely to avoid a larger implementation. Best-in-class strength remains the goal.

## E59 — Distillation convergence control on the same corpus

E56's recent train/dev policy KL is 0.566/0.583. The small gap and substantial
remaining error do not identify capacity, optimization, or target ambiguity.
Before a new architecture, test whether more optimization compresses the
existing teacher targets. After E58 completes, train for 50 epochs on exactly
its fresh 5,000-game corpus plus the same E56 replay shard and dev corpus.
Warmstart E56, training seed 800000009, same architecture, inputs, loss, batch,
and initial learning rate. The cosine schedule spans 50 epochs. This controls
training budget and schedule together; it does not isolate them separately.
Select by the same dev metric, with epoch zero retained. Compare the resulting
model to E58's selected lineage endpoint in 2,000 paired games at 3540000000,
128 simulations, depth 16, 14 threads. Use the same provisional point rule.
Keep strict results, train/dev fit, and total model-to-screen time. No new data
collection and no milestone in this control. The experiment asks whether a
longer fit is a useful next step; it is not an architecture search.

## E60 — Teacher target repeatability diagnostic

Hypothesis: Part of the remaining distillation KL may come from search target
variance across sampled hidden worlds. Keep the Observation and legal actions
fixed. On deterministic Strong trajectories (ordinary and first-six-turn blind
reservation stress), collect Main observations every eighth turn. For each,
run eight independent 800-simulation E56 teachers. Measure visit-policy TV,
argmax disagreement, and value-target range. All teachers receive Observation
only. This measures target repeatability, not playing strength or corpus
prevalence. High variance would support a larger change to belief aggregation
or target construction; low variance would direct attention to fit capacity.

**E58 completed:** 2,000 complete games,51.8% over E56;95% interval
47.49–56.11%. The registered provisional rule advances to native SHA
fd448a7fd66463a20235d75a2a621ce1d22fc17d7b89138c4fd9d938288233f1.
Strict gate retains E56. The fixed champion does not change. Fresh train
corpus has280,951 positions;dev56,128. Collection803.67+159.25s,
training119.53s. Epoch7 selected from10.

**E60 completed:**62 fixed observations,eight independent searches each.
Mean pairwise policy TV24.10%,mean TV to the mean17.42%,argmax
disagreement22.38%. Mean value-credit range0.05525. Ordinary and blind
stress cohorts are reported separately; this is not corpus prevalence or
proof of a causal strength limit. It supports a target-aggregation control.

An optional `--teacher-replicates` collector mode now averages independent
root policy/value targets. The first teacher alone chooses every trajectory
action and opening sample; all extra teachers receive Observation only. Its
16-game800-simulation check (908rows) keeps trajectories,inputs,masks,
outcomes and primary work identical. Default one-teacher data matches the
original E58 prefix exactly. Extra label work is reported separately.
The first check failed on a one-legal-action observation: no search target
is available. The fix uses the same one-hot action fallback and unknown
value mask as the original collector. Failed source/logs are preserved.
This mode is available but has no playing-strength result yet.

## E61 — Paired teacher-aggregation training control

E60 identifies substantial repeatability error in teacher policies. Test a
structural change to target construction, with two independent 800-simulation
teachers per observation. Regenerate all 5,000 E58 training trajectories from
E56 at the same setup/policy seeds. Only averaged policy/value labels may
change: require identical records, inputs, masks, and outcome labels across
all positions. The first teacher controls trajectories and opening sampling.
This keeps the successful position volume and avoids a quality/volume confound.
Use the exact E58 dev corpus and E56 replay shard, warmstart E56, 10 epochs,
seed800000009, and the same loss/selection/batch/learning rate as E58.
Teacher collection runs concurrently with E59's offline optimization. Report
all extra label work and collection time. This is a two-teacher target average,
not a change to runtime search or a claim of ensemble strength.

Fixed 2,000-game paired screen3560000000 at128/depth16/14threads against
E58's frozen10-epoch model gives the direct target-construction control. If
it passes the provisional50.5% requested-credit rule, also compare against
E59's selected lineage at3570000000 if that model differs from E58. Advance
only if the candidate passes both applicable screens. Preserve all strict
results. E56 stays the fixed champion. After these three attempts(E58,E59,E61),
freeze the endpoint and use the reserved3580000000,20,000-game milestone
against E56. No candidate selection from this milestone. The milestone sits
outside the inner model screens. Do not call an incomplete milestone a victory.

**E59 completed:**2,000 complete games,51.3% over E58;95% interval
47.11–55.49%. Provisional advance;strict retain. Selected epoch7 of50,
training827.44s under overlap with teacher collection. Train/dev KL0.5721/
0.5850,nearly unchanged from E58's0.5730/0.5843. This does not establish
a useful fit gain from50epochs. Keep the normal10-epoch budget. The
provisional model step is unconfirmed. The E61 target control continues.

E60's finite-replicate KL dispersion is0.1630 for single searches and
0.07913 for pairs averaged from the same eight-search set. This is a probe
cohort statistic,not a population noise floor or model-capacity estimate.
