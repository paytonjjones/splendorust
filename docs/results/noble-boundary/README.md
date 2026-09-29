# Last-seat noble boundary

E22 corrects E21's agent guard for a last-seat take that claims an already
eligible noble, reaches 15 prestige, and ends the game. The final-round flag
can be false before this take. The core rules and mandatory noble choices do
not change. Single and multiple eligible nobles are tested with invariant-valid
constructed observations and actual core transitions. These observations are
not recorded reachable histories. Earlier seats still require the next actor
to play; their block guard remains active.

The E21 gate seeds are reused only to compare ordered records after the narrow
correction. They are not fresh holdouts and provide no new playing-strength
or performance claim. Exact raw reports, independently recomputed summaries,
gate/build manifests, validation logs, and comparison hashes are retained.
The prior E21 evidence remains unchanged in `../two-player-policy/`.

Run the targeted regression:

```sh
cargo test --release --locked -p splendor-agents noble_threshold
```

The before/after production fingerprints apply to this worktree's source.
Benchmark feature files in another branch can change the fingerprint even
when agent choices are identical. See `validation.json` for source identity
and `record-comparison.json` for exact per-stage equality checks.
