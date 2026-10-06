# Additional random and fixed play speed

Both workloads pass the additional 20% target relative to the previous delivered
candidate, source commit 7de6146. This is the existing aligned adapter pipeline
on an Apple M4 Pro with one worker and unchanged release settings.

| Policy | Previous trajectories/s | Final trajectories/s | Additional gain | Paired timing bootstrap 95% |
|---|---:|---:|---:|---:|
| random | 103,703 | 139,352 | 34.38% | 34.19–35.61% |
| fixed | 86,284 | 106,040 | 22.90% | 22.73–23.35% |

Seven release repetitions alternate baseline and candidate order. Each uses the
same 240,000 fresh cases at master seed 111000001. Every timing window exceeds
one second. The paired bootstrap uses seed 20261006 and 10,000 resamples. These
intervals describe repetition noise on this shared host; they do not establish
performance on other machines or playing strength.

The baseline executable is byte-identical to the candidate executable in the
first-stage confirmation. The final checkout also retains the remote main work
through a merge. BUILD.json records both source identities, executable hashes,
compiler settings and every relevant Rust source hash. All measured final
records, decisions, turns and incomplete statuses match in all repetitions.
No unfinished game receives a winner.

The final implementation uses four-byte projection entries instead of 16-byte
(key, Action) pairs. Each entry contains the original numeric key and slot.
Integer sorting produces the same complete projected order. Selection decodes
the original action before checked application. Complete canonical enumeration
is still performed on each state and remains in the timer.

Core eligibility uses two constant tables for the published three- and four-bonus
noble requirements. Compile-time checks verify that dataset assumption. The
adapter uses the same helper for its post-purchase multi-noble stop check. Gold
purchase affordability sums all five deficits without early branches. Gold-free
membership selects one 64-bit word from the same 128-bit card mask. Observation
construction and its Decision wrapper are inlined; all returned fields and
redaction rules remain unchanged. No rules, action order, RNG, card IDs, engine
version, replay encoding, optional payments or return choices change.

A dedicated reference test compares every decoded projection entry and its order
with the original projection on more than 10,000 canonical Main states across
2/3/4 players. It covers hand sizes 7/8/9/10 and both gold-supply cases. Noble
eligibility matches the original requirement scan on 7,776 bonus vectors and
seven availability masks, including bonuses above the maximum requirement.
The existing full-action reference tests, transition tests, replay fixtures and
zero-allocation tests also pass.

Before final timing, broader trace checks covered 1,024 fresh random cases and
1,024 fresh fixed cases at master seed 110000001. Every projected legal-key list,
selected key, intermediate normalized state, final state and outcome matched.
TRACES.json and its archives retain this evidence. The timing runner additionally
checks the original 64-case smoke corpus per policy and all 240,000 normalized
final records in every repetition.

Separate full-choice native checks show:

| Workers | Native random gain | Native greedy gain | Shortest window |
|---:|---:|---:|---:|
| 1 | 30.58% | 1.85% | 1.047s |
| 4 | 31.89% | 2.61% | 1.663s |
| 8 | 32.36% | 2.15% | 0.970s |

These native checks use two players and seven alternating repetitions per
configuration. All final digests, decisions, turns and complete/blocked/capped
counts match. Setup and final digest remain inside native timing. Native greedy
is a different policy from aligned fixed; it does not have a 20% gain. The
8-worker random pilot reached the 1,200,000-case ceiling, so that row has windows
below one second and remains preliminary. All native samples and durations are
retained in native.json. No completion or playing-strength claim is made.

The exploratory one-repeat screens are retained below. They use the same
80,000-case corpus and have timing windows below one second. They are preliminary
and show failed branches as well as improvements.

| Screen | Random gain | Fixed gain |
|---|---:|---:|
| insertion | 0.81% | -1.11% |
| bitset | -5.37% | 8.08% |
| compact | 4.43% | 14.22% |
| masks | 34.19% | 19.32% |
| shared | 33.73% | 20.31% |
| grouped | 28.61% | 14.97% |
| threshold | 33.13% | 19.15% |
| word | 35.31% | 20.42% |
| observe | 34.97% | 21.12% |

Final local validation passes: format, strict release workspace Clippy with all
targets and features, 148 default release test executions, and 155 all-feature
release test executions. Strict Clippy exposed inherited Entity inference lints;
the row loop now uses enumerate with the same dot-product reduction order.
Frozen GELU coefficient literals and arithmetic remain unchanged, with a local
precision/constant lint exception. No model, policy or champion pointer changes.
GitHub Actions remains disabled, verified through its repository permission API.

See README.md for reproduction, PLAN.md for the hypotheses, BUILD.json for the
freeze, VALIDATION.json and logs for checks, and MANIFEST.json for artifact hashes.
The first-stage evidence in the parent directory remains historical evidence for
commit 7de6146; its manifests do not describe later source or script edits.
