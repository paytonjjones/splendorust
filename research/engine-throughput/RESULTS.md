# Canonical engine throughput results

The complete canonical Rust decision path exceeds the pinned AhinLendor C++
profile on all four fixed traces in both engine orders. The median gain is
4.8–11.4%. This result covers these workloads and this shared host; it is not
a general engine or search-strength ranking. Normal core transitions remain
allocation-free. No legal choice or rule was removed.

The measured bottleneck was complete action generation, especially Main and
Payment. Before production changes, full Rust replay took 5.242 us/game;
checked supplied-action replay took 1.119 us/game and traversal/initial clone
took 0.041 us/game. Cached generation took 40.8 ns/Main decision, 19.5 ns/Payment,
37.4 ns/Return, and 4.5 ns/Noble. Cached membership took 2.36 ns. Clone plus
checked apply took 14.05 ns, versus 4.12 ns for clone alone. These separate
cached workloads do not give an additive wall-time breakdown.

C++ took 2.650 us/game in the original replay and 2.353 us/game with typed
actions decoded before timing. Its regular mask generation took 14.4 ns,
return mask 3.53 ns, noble mask 39.6 ns, membership 0.69 ns, and colored-first
payment parity check 2.64 ns. C++ clone plus checked apply took 216 ns versus
179 ns for clone alone. Its dynamic vectors allocate during these clone probes;
their difference must not be reported as the sequential transition cost.
The named supplied-action replay profiles retain transition-only diagnostics.

The original Rust benchmark adds a membership scan before direct checked
apply. Normal arena callers previously enumerated and then used direct checked
apply without that scan. C++ similarly checks a generated mask and validates
again in applyMove; its original trace also decodes strings and checks automatic
payment inside timing. The faster predecoded C++ target retains its full mask
and checked transition. AUDIT.md identifies the Rust and C++ runtime callers.

Changes: precompute ordered take rows and copy them in bulk; share buying-power
inputs; intersect card-cost masks when gold is zero; skip payment recursion
only where there is one possible branch; align Action to eight bytes; and inline
small wrappers. Return and noble enumeration retain the original algorithms.
The exclusive-borrow Decision API ties an immutable complete list to its state
and consumes that proof on application. It replaces repeated direct validation
with membership validation. Checked supplied-action apply remains available.
Arena execution and classical search rollouts use Decision; cross-world search
root actions still use direct checked apply. Agents receive Observation only.

All choices and their order, explicit seven-byte wire encoding, RNG, card IDs,
rules, state transitions, and replay semantics remain unchanged, so ENGINE_VERSION
stays splendorust-v2. GameState stays 352 bytes. Action grows from seven to eight
bytes; ActionSet grows by 256 bytes to 2,056 bytes. No fused turn is required.

Each confirmation used seven repeats of 100,000 replays per trace. The second
batch reverses engine order for every trace. Traces were selected for coverage
before final timing, not for speed. Both batches retain complete Rust action
lists and every internal decision. Medians below are from the first passing
batch; the last column shows the independent reversed-order gain.

| Seed | Turns; Rust/C++ applies | Original Rust k games/s | Rust Decision k games/s | Original C++ k games/s | Predecoded C++ k games/s | Gain; reverse gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 424262 | 68; 117/71 | 194.0 | 435.6 | 365.7 | 402.2 | 8.3%; 6.3% |
| 424268 | 64; 113/64 | 207.0 | 476.4 | 402.7 | 453.4 | 5.1%; 4.9% |
| 424285 | 70; 123/76 | 193.8 | 398.4 | 344.5 | 380.1 | 4.8%; 5.8% |
| 424287 | 62; 105/65 | 235.3 | 484.7 | 391.6 | 435.0 | 11.4%; 8.4% |

| Seed | Original Rust ns/turn | Rust Decision ns/turn (ns/action) | C++ ns/turn (ns/native apply) | Rust repeat range; C++ repeat range, ns/turn |
| --- | ---: | ---: | ---: | --- |
| 424262 | 75.80 | 33.76 (19.62) | 36.56 (35.01) | 33.50–34.63; 35.87–36.83 |
| 424268 | 75.47 | 32.80 (18.58) | 34.46 (34.46) | 32.24–33.55; 34.09–34.82 |
| 424285 | 73.70 | 35.86 (20.41) | 37.58 (34.61) | 35.41–36.21; 37.40–38.90 |
| 424287 | 68.54 | 33.28 (19.65) | 37.08 (35.37) | 32.91–33.68; 36.77–37.89 |

Internal-operation times have different contracts: C++ combines purchase and
automatic colored-first payment, and splits compound colored returns. Complete
turns are the comparison unit. Rust still performs 117 decisions on the original
68-turn trace. Purchase rates range from 64.5% to 76.6%; traces include zero to
five Return decisions and zero or one mandatory Noble decision. On the original
trace, Rust generates 1,647 Main, 49 Payment, nine Return, and two Noble choices.
Main choices reach 35 across the suite; payment lists reach four choices and
return lists six. All four trace hashes, including the original hash, are exact.

The full optimized-enumeration plus checked-apply profile remains slower than
predecoded C++ on three traces. The measured gap closes with Decision and small
wrapper inlining. Merely reusing the stack buffer had little benefit; it never
removed heap allocation because the buffer was already allocation-free. The
zero-gold bitset change has no independently established gain. Early branches,
the first fixed confirmation (three traces below C++), and large-transition
inlining (slower on every trace) remain as negative evidence. Thirty scan runs
were initially rejected only by the old all-category coverage gate; all 32
complete traces passed exact parity after that gate was relaxed. Failed build,
Clippy, and probe assertions are also retained.

Actual caller check: three fixed 12,000-game random benchmark repeats for each
of two, three, and four players improved complete-game throughput by 23.3%,
21.2%, and 18.1%. Blocked counts stayed exactly 271, 2,072, and 1,564; unknown
outcomes were retained. The numerator counts only completed games, while time
includes every attempt. All 1,000 strong/greedy and 64 classical-search/strong
records are identical before and after, including trajectories and outcomes.
Search used 128 iterations, depth eight, width six. Its one timing pair is a
diagnostic, not a repeated search-speed or strength claim. Neural policies,
AlphaZero sources/models/records, champion pointers, and other jobs were untouched.

Correctness: exact material and deck snapshots at setup, every completed turn,
and final state; exact winners; ordered reference/optimized lists and selected
per-action states/observations; targeted independent payment and return oracles;
all-choice checks over 96 seeded paths with two to four players; 252-payment
capacity; gold returns; invalid actions/indices; turn-cap atomicity; allocation
test; golden replay/end-round/tie tests; and borrow compile-fail test. Four corrupt
post-turn snapshots and a duplicate setup record were rejected before timing.
Format, strict release workspace Clippy with all targets/features, 146 default
release tests, and 152 all-feature release tests passed with the locked toolchain.

Build/provenance: Apple M4 Pro, 14 CPUs; Rust 1.98.1 (LLVM 22.1.8), thin LTO,
one codegen unit; Apple clang 21.0.0, C++17 -O3 -DNDEBUG -flto; pinned Ahin commit
96e6f2daff83147495826c4a2073dc3c856cc9. Jobs owned by this work ran sequentially.
One-minute load ranged from 6.87 to 34.14 in the first passing batch and 5.52
to 9.19 in the reversed batch. Both passed every median; the host was not isolated.
Receipts bind sources, models, binaries, commands, counts, and raw timings. The
Rust profile binary hash starts 13f745885528; C++ starts faae4c8ab196; strict
original Rust baseline starts 4ab96b448a45. Full hashes are in the evidence archive.
The original baseline is rebuilt from 534cd40 with its original seven-byte Action;
only count arguments and the per-trace coverage gate are adapted. The restored
original benchmark remains separate from the optimized profiles.

Limits and remaining work: these are four deterministic two-player replay
traces, not diverse agent-driven trajectories or a broad engine ranking. Ahin
cannot represent arbitrary canonical payment choices or gold returns; these
cross-engine cases are unsupported and explicitly fail. Its automatic payment
policy was used only to select comparable traces, never as the Rust action
space. Three/four-player cross-engine parity was not run. Future work can add
gold-rich canonical-only performance fixtures and wider controlled-host replay
suites, and measure search speed with repeated policy workloads. Supplied-action
diagnostics do not establish a full-turn win. GitHub Actions remains disabled.

See README.md for reproduction, SUMMARY.json and REVERSED_SUMMARY.json for full
statistics, VALIDATION.json and REVIEW.md for checks, and EVIDENCE.json for the
archive manifest. PLAN.md retains the six-hour/45 CPU-minute budget and its
bounded branch extension. Work finished within the six-hour budget.
