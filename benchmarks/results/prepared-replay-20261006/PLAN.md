# Prepared checked replay comparison

Hypothesis: removing C++ move construction and noble lookup from timing gives
a closer comparison of the engines' checked supplied-move paths. Do not change
production engines, agents, rules, or the old benchmark profiles.

Before timing, prepare native Rust Actions and native AhinLendor Moves for each
of the four registered complete traces. Expand C++ token returns and resolve
noble slots once. Verify setup, every complete turn, final state, and winners
outside timing. Check that native apply counts match the original traces.
Both timed paths clone the same engine's initial state for each replay, apply
all prepared native moves through the engine's checked entry point, and keep
the completed-turn state observable. No extra legal enumeration, policy,
record construction, trace conversion, or parity snapshots belong in timing.

Freeze four seeds: 424262, 424268, 424285, 424287. Run seven repetitions of
1,000,000 complete replays per engine and trace, then reverse trace and engine
order and repeat. Preserve all samples, raw logs, source and binary hashes,
compiler versions, host load, trace hashes, checks, and failures. Compare
complete game replays/s, not internal applies/s. State copy and native checked
transition costs remain included; different internal steps remain engine design
differences. This is not a general game simulation or playing-strength test.

Budget: two hours elapsed and 20 CPU-minutes of planned timing. One owner runs
heavy work in sequence. Run required Rust checks before measurement because
the Rust benchmark example gets a profile selector. Keep old evidence intact.
Leave the main README table unchanged until the user reviews the new preview.
