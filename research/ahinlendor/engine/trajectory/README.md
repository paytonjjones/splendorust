# Exact full-turn raw-engine trajectory

This harness complements the primitive and single-action benchmarks in the
parent `engine_comparison` example. It replays one fixed legal full game through
SplendoRust and AhinLendor. It is a raw-engine workload. It runs no bot, search,
neural network, or strength test.

The Rust writer uses the fixed setup seed `424262` by default. It chooses a
deterministic policy. It buys a visible affordable card, then a reserved
affordable card; it forces one deck reservation and one visible reservation;
it otherwise takes tokens toward the cheapest visible card. It pays colored
tokens before gold, returns colored tokens only, and selects the first legal
noble. The seed and policy must produce take, visible and deck reserve, visible
and reserved buy, payment, return, noble, and terminal coverage. The writer
fails if required coverage is missing, if it has no legal action, or if a
required return needs gold.

The trace contains the full predetermined decks and blind reservations. It is
private benchmark input for the two raw engines only. Never pass it to a bot or
use it in a strength comparison. The Rust writer serializes an exact canonical
material snapshot at the start, after every completed player turn, and at game
end. The C++ replay checks each full snapshot and a compact digest before it
times anything. Snapshots include every card identity and deck order, tokens,
bonuses, scores, reservations, nobles, current seat, turn, phase, and final-round
state. It sorts the purchased-card and claimed-noble sets because Rust stores
them as bit sets while Ahin stores them in insertion order.

Both timed workloads repeat the same recorded game 10,000 times for each of
three repeats. Each engine enumerates its legal actions before its selected
native action and applies the transitions. It does not time policy selection
or snapshot comparison. Rust reports canonical actions and apply calls. Ahin
reports native apply and legal-enumeration calls. Ahin combines purchase and
colored-first payment in one transition; it splits a canonical compound return
into one transition per colored token. These internal operation counts are
different by design. Compare completed turns and games per second for this
fixed trace, then inspect operation counts to understand the work performed.

Build and run with:

```sh
python3 research/ahinlendor/engine/trajectory/run.py
```

The runner uses a separate ignored Rust target directory, the pinned Ahin
checkout at `96e6f2daff83147495826c4a2073dc3c9c856cc9`, release Rust settings,
and C++17 `-O3 -DNDEBUG -flto`. It writes command logs, the private trace, raw
timing CSV, source and binary hashes, toolchain versions, and machine details
under `local/research/ahinlendor/engine/trajectory/runs/seed-424262/`. Give
`--output-dir` a new empty path to keep a second receipt. It does not overwrite
an existing non-empty receipt.

The 68-turn seed used for the workload reached every required phase and
action category. One trace is a representative workload, not a broad engine
ranking. Repeat with more preregistered setups and controlled host load before
making a general performance claim.
