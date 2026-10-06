# Independent review

Three bounded Luna helpers worked under one owner. The owner scheduled all
builds, tests, and timed CPU work in sequence. No helper ran a GPU job or
contacted another person.

The Rust helper built the initial profiling path, ordered enumeration changes,
and borrowing Decision API. The audit helper independently reviewed legal
choice preservation, gold-payment recursion, turn-cap atomicity, observations,
and callers. It found a changed wants_public_history call order in the arena;
the owner restored the original order. The final read-only review confirmed
that wants_public_history follows select_action, Decision.observe delegates
to the same redaction method, and both apply methods preserve the turn guard.
It found no remaining correctness issue. The initial alleged payment-recursion
fault was retracted after the reviewer traced the separate recursive helper.

The C++ helper built the component profiles and reviewed full-mask generation,
input/output barriers, unchanged original replay, and exact snapshot checks.
It found duplicate setup records could overwrite previous entries; the owner
added explicit rejection. The complete-trace parser relaxes only the original
requirement that every trace include all eight categories. Gold returns remain
unsupported and cause a failure. No upstream C++ engine file was changed.

Action is aligned to eight bytes for in-memory list writes. Review found no
raw-layout serialization or transmute. Encode/decode use the same explicit
seven-byte wire fields. Tests compare ordered choices, transitions, redacted
observations, outcomes, golden replays, and allocations. The final inlining
change affects small wrappers only. The large-transition inlining experiment
was slower on all traces and was reverted.
