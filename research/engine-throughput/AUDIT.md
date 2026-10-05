# Timed-path audit before engine changes

The original Rust trace calls legal_actions, ActionSet::contains, and apply_action
for every action. apply_action already uses a direct phase-specific predicate.
It does not regenerate the list. Normal arena execution and sampled-world
rollouts enumerate choices then apply the selected action without the contains
scan. The baseline adds that scan. ActionSet is stack storage; a new buffer does
not imply an allocation or a full clear of its capacity.

The C++ baseline calls getValidMoveMask then checks one bit. applyMove validates
the supplied move again. Purchase replay also computes colored-first payment,
checks it against the canonical trace, and checks post-transition token deltas.
The string action decoder and counters are inside its timed loop. Rust has
already decoded typed actions. A named predecoded C++ profile will remove this
harness cost; it must not silently replace the original baseline.

Rust runtime callsites: arena src/lib.rs game loop; agents src/lib.rs sampled-world
rollout; agents src/environment.rs Canonical::legal and Canonical::apply. Root
search candidates cross into new determinizations, so a stale validation token
must not bypass checks there. Agents continue to receive only Observation.

A safe enumerated-action capability would borrow the state exclusively, keep
its action list immutable, and consume itself on selection/application. This
is optional and will only be implemented if measured costs justify it. Do not
add an unchecked public action API or expose private state to agents.

The C++ policy cannot represent arbitrary payments or gold returns. Cross-engine
trace parity therefore covers a shared subset. Canonical-only tests must cover
all payment and return choices, noble choices, reservations, endings and ties.

Verified C++ callers at the pinned checkout: py_splendor.cpp step (lines 609-617)
builds a mask, checks its selected bit, then calls applyMove. native_endgame.cpp
(lines 347-370) generates/orders masked moves, then calls checked applyMove
for search children. native_mcts.cpp (lines 2362-2366) selects from a stored
node mask before checked applyMove. State-vector encoding also calls mask
generation. Thus mask generation/selection and transition validation occur
in real callers, although not every search edge regenerates a mask. The raw
trace's string decoder and colored-payment parity checks are harness costs.
No C++ bot/search strength or inference comparison was performed.
