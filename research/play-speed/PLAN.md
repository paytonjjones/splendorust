# Random and fixed play speed

Baseline: e429c72, current checkout, locked pinned release build, thin LTO,
one codegen unit. Goal: at least 30% more attempted trajectories per second
for both random and fixed play. Preserve exact ordered canonical choices,
policy RNG, setup, outcomes, and incomplete-game accounting.

Hypothesis: ordered table-based legal generation and shared affordability
checks reduce core work. Reuse the verified implementation from 0de6afe,
then measure against this checkout. The aligned adapter also allocates a
projection vector each turn. A fixed-capacity buffer can remove that cost
without changing any projected choices or checked transitions.

Measure the existing seal256-intersection-v1 random/fixed adapter pipeline
and full-choice native random play separately. Keep the existing benchmark
contract. Core enumeration remains complete; profile restrictions are policy
choices only. Use matched corpora, seven alternating release repetitions,
and final-state/operation-count equality. Check complete traces before timing.
Record binary/source/corpus hashes, raw times, machine and shared-host load.
Retain rejected experiments. No playing-strength or external engine claim.

Required validation: format, strict workspace Clippy, locked release workspace
tests, all-feature tests, ordered reference enumeration and transition parity,
allocation checks, and exact baseline/candidate traces and records.

Native random caller hypothesis: an index chosen from the current complete legal
list need not repeat direct action validation. Use the exclusive-borrow Decision
API with apply_index. Arena agents use the guarded action API. This changes no
policy choice. The aligned contract keeps checked direct transitions.
