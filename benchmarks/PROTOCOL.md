# Splendor engine benchmark protocol v1

This protocol defines what can support a speed claim. A native engine timing is
useful evidence, but it does not by itself show that two engines do the same work.
The report must state which gates passed and which measurements remain preliminary.
The existing evidence in `BENCHMARKS.md` and `docs/results/` remains unchanged.

## 1. Comparison groups and entry gates

Use a separate comparison group for each workload, player count, policy, ruleset,
timing scope, and worker model. Rank engines only inside a group that passes all
of these gates:

1. Same functional 90-card and 10-noble data, token supply, market size, reservation
   cap, ten-token limit, and 15-point final-round rule.
2. Same legal choices: token takes, optional gold payments, exact excess returns,
   blind and visible reservations, mandatory noble selection, and ties by fewest
   purchased cards with shared exact ties. Check the interpretations in
   `VALIDATION.md`; do not treat an external implementation as an oracle.
3. Same player count. Two-, three-, and four-player games are separate workloads.
4. Same policy distribution or deterministic policy, including decisions made
   automatically inside an engine. Same numeric seed alone does not establish
   the same setup or policy: RNG algorithms and action order can differ.
5. Same measured operation and outcome accounting. A whole player turn and a
   payment subdecision are different units.
6. Valid runs: no illegal state/action, missing data, fabricated pass, fabricated
   winner, or unreported cap. A rules mismatch cannot be fixed by omitting its
   failure counts from the output.

A candidate that fails a gate stays in the inventory and native reference table.
Its result has `comparable: false`, a reason, and no cross-engine speed ratio or
rank. A compatible opening action does not certify a compatible complete game.
No comparative ranking is required when no external engine passes these gates.

### Optional setup and ambiguous-position alignment

Core feature `benchmark-compat` exposes setup injection and an explicit
experimental no-action pass. It does not change normal `ENGINE_VERSION`,
`Action`, `legal_actions`, or replay behavior, even when compiled in. The current
default engine is `splendorust-v2`; the separate profile version is
`splendorust-v2-benchmark-compat-v1`. Reports that use these hooks must record
this version plus the exact profile. They are
different workloads from published-rule games.

`GameState::new_benchmark_setup` accepts every card ID exactly once in its own
tier, in first-to-last draw order, and exactly player-count plus one unique
noble IDs. It validates complete permutations before construction. First four
draws per tier fill visible slots in order. External adapters must map functional
card/noble tuples to their own IDs; raw IDs are not a cross-engine mapping.
Policy code still receives Observation only.

`GameState::apply_no_action_pass` succeeds only in a nonterminal Main phase with
an empty generated action set. It advances the ordinary turn/final-round path;
it neither appears in the legal action list nor creates a new replay Action.
The caller must record passes in its separate versioned corpus, retain their
counts, and stop a full no-action cycle without awarding a stalemate winner.
A normal final-round finish stays distinct from a blocked full cycle. A run
with this extension cannot be presented as a published-rule result.

At `turns == u32::MAX`, an otherwise permitted experimental pass returns
`TurnLimit` without state mutation, as normal v2 actions do. Invalid passes
still return `IllegalAction`. Counter capacity is a resource error, not a
terminal game or winner. A pass starting at `u32::MAX - 1` can reach capacity
through the normal end-turn path. Preserve historical v1 reports and schedules
with their original versions; current v2 evidence does not relabel them.

For a complete-game comparison, prefer the actual rules with matching explicit
payment, return, and noble choices. An optional profile can align an ambiguous
no-action situation, but it cannot conceal another rule mismatch. A candidate's
automatic choice may be replicated by a documented common policy if both
engines execute that exact policy and normalized traces agree. Such a policy
measures its restricted action path, not enumeration of all legal choices.

## 2. Workloads

### Native random legal-play trajectories

Enumerate native legal actions and select uniformly with a seeded policy RNG.
Record whether choices are complete turns or separate phases. If the API selects
payment, returns, or nobles automatically, disclose each rule and exclude it from
the full-choice comparison group. Native random play can still measure its own
engine. It includes legal generation, minimal random selection, state transition,
and game setup. It excludes AI evaluation or search.

Stop at normal terminal state, empty legal action set, illegal transition,
explicit error, or a fixed cap. Use `complete`, `no_legal_action`,
`decision_limit`, `illegal`, `unsupported`, and `error` as distinct outcomes.
Use a 20,000 native-decision cap unless a candidate needs a documented cap in
complete turns; that candidate belongs to a different group. Do not call a cap a
draw or victory. Count all started trajectories, including unfinished ones.

### Deterministic fixed-policy trajectories

A deterministic policy must specify action priority and tie order by semantic
action fields, including payment, return, and noble choices. "First legal action"
is a native diagnostic, not a common policy when enumeration order differs.
Likewise, Splendorust `greedy` is a local AI-policy baseline unless another
adapter implements the same observable-state function and passes trace checks.
Label that workload `native_fixed_policy`, and include its evaluation cost.

For a common fixed policy, first map cards by their functional tuple, not native
ID. Inject the same initial deck order, nobles, first player, and action schedule
when APIs allow it. Verify normalized state and legal-choice sets before each
decision. Keep states with private reservations private from policy code. If
injection or semantic action mapping is not possible, mark the common workload
unsupported rather than claiming fixed-policy equivalence.

### Restricted common transition or enumeration workload

A narrower comparison is valid when complete-game gates fail only outside a
precisely bounded state corpus. Store a corpus with identical normalized states,
actions, expected successor states, and a hash. For example, opening takes can
exclude purchases, reservations, nobles, and returns explicitly. Both engines
must verify every input and output against the corpus before timing.

State which costs the operation includes: input-state copy, legal generation,
action validation, apply, output-state copy, or checksum. Keep those costs the
same across implementations. Do not subtract two tiny timings to infer apply
cost. Use a checksum or equivalent mechanism to prevent dead-code removal.
Never extrapolate an opening-only result to complete-game speed.

The implemented common group is `checked-opening-copy-take`:

- Two players; opening colored bank `[4,4,4,4,4]` and five gold tokens;
  empty player hands, no discounts, reservations, purchases, or owned nobles.
- Clone the engine's full native opening state, then take one white, one blue,
  and one green token. Each timed iteration starts from the same untouched
  opening state. Initialization and card loading are outside it. This one-action
  corpus does not represent other token actions or later phases.
- Include native state clone, native apply validation, and apply work. Exclude
  legal enumeration, RNG, search, corpus conversion, JSON, and output. Consume
  the result to prevent dead-code removal. Record the exact checksum workload.
- Normalize color order and player numbering. Verify colored/gold bank, every
  player's tokens, current player, and completed-turn increment before timing.
  Splendorust uses white/blue/green/red/black/gold order; seal256 uses
  red/green/blue/white/black/gold order. After the action player zero has one
  white/blue/green token, those bank piles have three, and player one is active.
  Splendorust's completed-turn count is one. seal256's round count remains zero:
  normalize completed turns as `round * num_players + player_to_move`.
  Preserve untouched opening fields within each implementation.
- Card/deck order does not affect this action. A difference there can be outside
  this restricted gate only because no purchase/reservation/refill occurs.
  Full native state clone still has its implementation's natural size and cost.
  State the size and scope where available. This is an opening clone-and-apply
  claim, not complete-rule equivalence, legal-generation speed, or game speed.

The adapter's fixture checks are the entry gate for this group. An unchecked
take helper and a validated public apply function are different contracts;
record which path each adapter uses and do not rank them together unless their
validation work is comparable. Additional counters or data copied by one engine
must be disclosed; do not remove them to improve its result.

seal256's native apply function has validation disabled. Its checked wrapper
calls native `verify_action` before native `apply_action` in every timed
iteration. The validator is private upstream: a recorded interface-only header
patch makes it public. Retain the patch/hash and identify this exposure in the
external manifest. The patch changes access, not validation rules or apply
behavior. Splendorust checks inside its public apply function. Python's native
unchecked take stays in `unchecked-opening-reference` and receives no ratio
against this checked group.

The common output operation includes each native state's destruction. Rust uses
persistent Rayon dispatch/reduction; C++ starts and warms its threads before
timing and includes release/join. Those small scheduling costs differ and must
be disclosed even at multi-second batch durations. Rank by worker count
separately; do not imply an identical scheduling mechanism.

### Search workloads

Keep search outside the engine table. Use fixed simulation counts, not a soft
wall-clock deadline, for reproducible runs. Record simulations per main decision,
rollout depth in complete turns, root width, rollout policy, evaluation,
determinization method, internal thread count, and opponents. Count actual
simulations when the engine can stop early. A "simulation" can mean a different
amount of work in another engine. Equal count does not establish equal compute
or search quality. Report unsupported search benchmarks as gaps.

Splendorust search is flat root UCB with fresh hidden-state sampling. Its `mcts`
alias does not mean persistent-tree MCTS. Report search decisions/s,
simulations/s when instrumented, latency, and outcomes separately. A search speed
claim needs the same states, search definition, and budgets; an agent-strength
claim needs a separate valid tournament.

The implemented native `search32` workload uses search in every seat at 2, 3, and 4 players: 32
simulations at Main decisions with more than one legal choice, width six,
strong rollout, engine evaluation, and no time cap. The rollout horizon is eight
completed player turns, with an additional 32-native-decision guard per rollout.
Search itself is serial inside each game; arena workers run separate games.
Non-Main and single-choice decisions use the deterministic fallback without
simulations. Actual cumulative simulations are reported. The workload's native
decisions/s includes those fallback decisions; it is not search invocations/s.

## 3. Seed schedules and reproducibility

Every result stores the exact seed start, schedule identifier, game count, cap,
policy, and RNG algorithm. Generate seeds by game index before worker assignment;
worker index must not change a game's setup or policy stream. Repetitions reuse
the same corpus to estimate machine timing noise. A separate disjoint corpus can
measure sensitivity to game length and outcomes.

Existing Splendorust schedules are different and must stay distinct:

- New native worker (`benchmark_worker_v1`): setup seed is the first SplitMix64
  output from state `(master + i) mod 2^64`; random policy RNG starts at
  `setup_seed XOR 0xd1b54a32d192ed03`. Each game appears once, without arena seat
  rotations. Search seat `j` starts at `(policy_seed + j) mod 2^64` and uses a
  fixed 32-simulation configuration. Greedy is deterministic and uses no RNG.
  This applies to random, greedy, and search games. Its separate `setup`
  workload uses raw `(master + i) mod 2^64`; its opening fixture uses seed 42.

- Direct core loop: setup seed `(master + i) mod 2^64`; selection RNG starts at
  `i`. The RNG is SplitMix64 with rejection sampling for bounded indices.
- Arena: for `n` players, block `b = floor(i / n)` and rotation `i mod n`; setup
  seed is the first SplitMix64 output from state `(master + b) mod 2^64`.
  Identity `j` gets a separate RNG seed equal to the first SplitMix64 output
  from `setup_seed XOR (((j + 1) * 0xd1342543de82ef95) mod 2^64)`.
  Each setup has all `n` seat rotations; game counts must be divisible by `n`.

The RNG step adds `0x9e3779b97f4a7c15`, then applies the two multiply/xor stages
in `crates/splendor-core/src/rng.rs`. Use the checked-in implementation rather
than a language's built-in RNG as a substitute. Native external schedules may
use another RNG; record that difference. Numeric seed equality does not justify
a paired cross-engine confidence interval.

Retain source commit, dirty status, source/adapter fingerprints, data hashes,
exact commands, dependency lockfiles, and per-repetition outcome/checksum records.
For a common corpus, retain its content hash and action/state mapping version.
Re-run the same corpus with one and multiple workers; deterministic counts and
record hashes must agree before calling worker scaling reproducible.

## 4. Timing scopes and denominators

Use a monotonic high-resolution clock. Emit JSON and logs after the timed loop.
Exclude UI, network, database, training, diagnostic logs, and audit checks from
speed measurements. Run audit checks separately on smoke fixtures. Do not remove
necessary transition validation from one engine unless the same unchecked
contract is available and identified for all engines in that group.

Record setup/install and build wall times outside the run. Record process wall
time separately from the internal measured loop. Import, initialization, card
loading, model loading, and pool creation must each have a stated scope. Do not
derive tiny startup time by subtracting coarse clocks; call the residual
`process_overhead` if that is all that is observed.

Use explicit fields:

| Metric | Numerator / denominator |
|---|---|
| Trajectories/s | All started trajectories / timed seconds |
| Completed games/s | Normal completions / timed seconds |
| Native decisions/s | Successfully applied native decisions / timed seconds |
| Complete turns/s | Completed player turns / timed seconds, if available |
| Mean batch time per trajectory | Timed seconds / all started trajectories |
| Per-game latency | Direct elapsed time for each trajectory |
| Search decisions/s | Search decisions / search-workload timed seconds |
| Simulations/s | Actual simulations / search-workload timed seconds |

`timed_seconds / games` is an amortized batch metric, not a per-game latency
distribution. Measure per-game latency in a separate instrumented run because
clock calls can alter a very fast loop. Report p50, p95, p99 and sample count
when measured. Give separate completed/unfinished latency distributions when
possible. If there are no direct measurements, mark the percentiles unavailable.

Splendorust's existing arena `games_per_second` counts requested trajectories.
Its `decisions` includes Main, Payment, Return, and Noble phases. Its reported
runtime includes pool creation and record/report assembly, and excludes the
later JSON serialization. It is a native arena batch measurement, not pure
apply throughput or persistent-pool steady-state throughput. The existing CLI
`benchmark` also runs core microbenchmarks before arena timing; process duration
must not replace an internal workload duration.

## 5. Single-worker and multiple-worker runs

Measure one worker and a fixed multi-worker setting on the same host, corpus,
binary, build flags, and total work. State whether workers are threads,
processes, or internal search workers. Do not label multiple Python processes
as multiple threads. Do not imply process scaling is equivalent to native
shared-memory thread scaling. Record physical and logical CPU count; hybrid
performance/efficiency cores can affect scaling.

Persistent pool timing excludes worker startup and stops after all workers
finish the assigned workload. If a harness creates a pool for each timed batch,
label it `batch_including_pool`, retain that cost, and keep it in another group.
Do not reuse a serial elapsed time to estimate parallel performance. Calculate
observed scaling as the same workload's one-worker time divided by its
multi-worker time. No linear-scaling promise follows from one machine.

The new Splendorust native JSON worker creates its pool before it reports ready.
Each request uses that pool and starts the timer after request parsing. The
timed native loop includes per-game setup, legal generation, policy, transitions,
and result collection needed for counts/checksums. It excludes worker launch,
pool creation, JSON parsing, JSON serialization, and disk writes. Save worker
startup separately. Direct per-game clock measurements use a separate latency
mode: they include setup and play, but exclude queue wait, final digest, and
native state/agent destruction. Batch throughput includes final digest and
destruction. Latency probes report the sample count and all outcome counts;
pooled completed/unfinished percentiles must be labeled as pooled when they
are not split. Confirm these boundaries against each result's adapter hash.
This differs from the old CLI arena batch scope described above; keep old and
new measurements distinct.

## 6. Run order, repetitions, and uncertainty

1. Build optimized/release with locked dependencies. Preserve build commands and
   compiler/interpreter versions. Rust uses the repository's pinned toolchain,
   thin LTO and one codegen unit. Record C/C++ flags and Python implementation.
2. Run a small validation corpus, all supported player counts, and edge fixtures
   for rules claimed by a comparison group. Replay or re-run to verify counts
   and hashes. Check data completeness before long timing.
3. Run one untimed warm-up and a pilot for each configuration. Select a fixed
   work count that targets at least one second per measured repetition; target
   five seconds where practical. Do not switch to a wall-time game cap because
   that changes the seed corpus with machine speed.
4. Run at least seven independent measured repetitions. Alternate or rotate
   engine/configuration order with a documented order schedule. Do not run
   benchmark workers concurrently with another engine, build, audit, or search.
5. Preserve every repetition. Record unusual contention, thermal conditions,
   power mode, and failures. Re-run suspect repetitions only with a documented
   reason; retain the originals.
6. Report median elapsed time, range, and median repetition rate. Give a 95%
   bootstrap interval over repetition values if calculated; store bootstrap
   seed and resample count. Do not confuse machine-noise intervals with rule
   validity or cross-host portability. Correlated repeats on one machine do
   not establish general hardware performance.

Shorter repetitions or fewer than seven repetitions remain measurements, but
label their confidence preliminary. If the target duration is missed, report
the observed duration rather than claiming it was met. If outcome or trajectory
hashes vary at a fixed budget, resolve the cause or mark the run non-reproducible.

## 7. Metadata and result checks

Record timestamp, CPU model, architecture, physical/logical core count, OS
version, available memory, compiler/LLVM or interpreter version, optimization
flags, thread/process count, engine commit/version, license, adapter hash,
source fingerprint, build command, run command, working directory, policy,
players, seed schedule, cap, warm-up/pilot work, repetition count, raw durations,
outcomes, checksum, timer scope, and concurrent work notes.

Validate `complete + no_legal_action + decision_limit + illegal + unsupported +
error == started`. An unhandled engine crash is an error, not zero games.
Transitions count only successful applications. Check that completed-game rate
does not exceed trajectory rate. A normal completion requires the advertised
terminal rule; a timeout cannot count as completion. Retain stderr and exit code
when they explain a failure, with no secrets or unnecessary logs.

## 8. Adapters and report

Keep upstream source in isolated ignored directories. Check in retrieval,
build, and adapter code separately. Pin commits and dependencies; record license
or missing license. Build only engine/search components needed by a workload.
Do not add UI, training, network, database, or heavyweight ML dependencies to
Splendorust. If a candidate cannot be built without them, retain it as a gap.

An interface patch must be small, recorded as a patch with its hash, and limited
to exposure or instrumentation. Do not change gameplay, policy, data, or internal
optimization to improve a reference result. Explain unavoidable portability
patches. Preserve the untouched commit and a clean diff of the adapter changes.

Publish a comparable-workload ranking table and an unranked native reference
table. Each row states scope, player count, worker model, policy, completion
fraction, throughput, latency scope, uncertainty, and limitation. State which
engines built, which were measured, which gates failed, and which were not
measured. Unsupported workloads are explicit gaps, not invented results.
The baseline claim must be conditional on the validated workload and host.
The next step is the largest unresolved gap: common state/action fixtures,
complete rules compatibility, direct latency, longer timings, or an additional
candidate. Native ratios from incompatible games cannot establish that
Splendorust is faster than another complete Splendor engine.
