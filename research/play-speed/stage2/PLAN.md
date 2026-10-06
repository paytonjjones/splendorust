# Another 20% random and fixed play gain

Baseline: previous final-aligned binary from the first optimization, SHA-256
in the original confirmation.json. Source commit 7de6146 records that state.
The current remote main is merged before the next production change. Its core
and aligned worker are unchanged by that merge. Use the pinned locked release
build and the same gameplay timing boundary.

Hypothesis: the CPU sample identifies projected-action sorting as the next
large cost. Replace the generic comparison sort with a short insertion sort,
then consider sorting disjoint key ranges separately if needed. Preserve exact
projected numeric order, random draw count and fixed-policy tie handling.
Always enumerate the complete canonical legal list and retain checked apply.
No hidden data, rules or policy restrictions change.

Use 80,000 matched screen cases, followed by seven alternating repetitions on
at least 160,000 fresh matched cases. Success requires at least 20% more
trajectories/s for both random and fixed relative to the previous final binary.
Check complete legal keys, selected keys, intermediate states and statuses on
smoke and broader fresh traces before timing. Preserve failures, hashes, load,
raw results and the machine-noise bootstrap interval.

Before pushing main, run required local format, strict workspace Clippy and
locked release tests, default and all features. Verify source hashes and final
benchmarks. Fetch again, preserve any new remote changes, and push main without
force. Keep GitHub Actions disabled.

The simple insertion-sort screen did not meet 20%. Next hypothesis: semantic
keys occupy disjoint small ranges (visible buys, reserved buys, takes, visible
reservations). Collect membership bits while projecting the full legal list,
then consume bits in ascending order. Card IDs map to their current public slot;
a const ternary table maps take keys to quantities. This avoids comparisons
entirely and preserves the exact original projection and sorted order.

The bit-mask projection screen gained about 8% fixed but lost about 5% random.
It did not meet the target. Next hypothesis: (u32, Action) entries occupy 16
bytes and use a generic comparator. Store each projected choice as one u32:
high bits contain the same numeric key; low bits contain the original slot.
Sort integers and decode the chosen action. Decode every entry for trace and
reference checks. This keeps projection, sorting and checked apply inside timing.

Compact entries alone gained about 4% random and 14% fixed, below target.
The compact random CPU sample identifies core noble eligibility (98 leaf
samples) as a material remaining cost. Test precomputed per-color eligibility
masks, intersected with available nobles, plus branch-free gold affordability.
The masks clamp bonuses at the maximum published noble requirement (4).
Use exhaustive bonus-boundary/reference checks. Keep exact eligibility and
complete action order; these are implementation changes, not rule changes.

Combined compact entries, noble masks and branch-free gold affordability gained
34% random and 19% fixed in the preliminary screen. Reuse the same pure public
noble-requirement helper for the adapter's post-purchase multi-noble stop check.
This removes the duplicated requirement scan while preserving the exact stop.

Shared-mask screen: about 34% random and 20% fixed. Test disjoint compact-key
buckets to increase fixed-play margin: sort purchases, takes and reservations
separately, then concatenate in the same numeric order. All entries remain
materialized and sorted within the timed projection; no fixed-policy shortcut.

Grouped integer sorting was slower (29% random, 15% fixed gain). Revert it.
Test two threshold masks for noble eligibility: published nobles use only
uniform nonzero thresholds 3 or 4. Build a five-bit bonus>=3 mask and bonus>=4
mask, then look up eligible nobles for each threshold. Compile-time assertions
and exhaustive bonus-boundary tests preserve the dataset assumption. This
replaces five indexed requirement-mask loads with two compact table lookups.

Gold-free affordability hypothesis: testing an arbitrary bit in a u128 requires
more ARM integer work than selecting its low/high u64 word and testing one bit.
Test a selected-word membership check. Preserve card IDs 0..89 and all exact
capacity masks. Existing all-card reference enumeration checks cover both words.

Threshold mask and word membership screen: 35% random, 20.4% fixed.
The compact profile also samples GameState::observe as a material leaf cost.
Test inline observation construction so compiler dead-field elimination can
remove copies unused by a caller. The public Observation value, redaction and
agent boundary remain identical. Retain only if measured improvement remains.

Strict all-feature/all-target Clippy found inherited Entity inference lints.
Keep frozen GELU coefficient literals and arithmetic unchanged, with a local
precision/constant lint exception documented on that function. Express the
output-row loop with enumerate without changing dot-product reduction order.
This is lint maintenance, not a policy or model change. Validate through the
workspace tests; no new strength experiment or champion update is requested.
