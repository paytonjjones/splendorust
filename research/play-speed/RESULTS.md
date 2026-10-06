# Random and fixed play speed results

The 30% target passes for both named workloads in the existing
`seal256-intersection-v1` aligned adapter benchmark. Baseline: e429c72.
This result measures the adapter pipeline on this Apple M4 Pro, with one worker.
It does not mean that every native policy or engine workload improved by 30%.

| Policy | Baseline trajectories/s | Candidate trajectories/s | Gain | Paired timing bootstrap 95% |
|---|---:|---:|---:|---:|
| random | 67,310 | 99,510 | 47.84% | 44.84–49.05% |
| fixed | 47,388 | 85,594 | 80.62% | 78.23–82.38% |

Seven release repetitions alternate baseline/candidate order. Each uses the same
160,000 fresh cases at master seed 107000001. All timing windows exceed one
second. The intervals describe paired repetition noise on one shared host.
They are not cross-host guarantees or playing-strength intervals.

Core changes reuse the ordered table enumeration and Decision API from 0de6afe.
Legal generation shares affordability work and preserves every payment, return,
reservation and mandatory noble choice in the same order. Action storage uses
8-byte alignment. Direct checked apply remains available. Arena and native
benchmark callers use Decision to keep selected actions tied to their state.
Agents still receive observations only. The aligned adapter keeps checked direct
transitions and replaces its per-turn projection Vec with fixed-capacity ArrayVec.
No rules, RNG, action order, replay encoding or engine version change.

The baseline fixed-play CPU sample shows substantial projection-buffer growth
and allocator work. The preliminary core-only screen gained 4.00% random and
14.38% fixed, which missed the target. The subsequent buffer screen gained
47.59% random and 79.14% fixed. These are one-repeat screens, not final claims.
The final confirmation above uses fresh seeds and the final source state.

For each policy, the 64-case smoke trace matches baseline legal-key lists,
selected keys, intermediate normalized states and outcomes. All 160,000 final
records match in every timing repetition. Counts, turns, decisions and all
incomplete statuses are retained. No blocked or unsupported case gets a winner.
Raw records, hashes and timings are in confirmation.json and its record archives.

The separate native worker measures full canonical random play and native greedy
play, with setup and final digest inside timing. Native greedy differs from the
aligned fixed policy. Its measured gains are:

| Workers | Players | Random gain | Native greedy gain |
|---:|---:|---:|---:|
| 1 | 2 | 27.66% | 8.20% |
| 1 | 3 | 25.55% | 8.61% |
| 1 | 4 | 24.60% | 8.67% |
| 4 | 2 | 25.00% | 7.90% |
| 8 | 2 | 24.48% | 8.38% |

Native final digests, decisions, turns and all status counts match for every
baseline/candidate pair. One-worker checks cover 2/3/4 players; scaling checks
cover two players with 4/8 workers. Some native windows are below one second
because pilot calibration changed with warm execution and the 200,000-case cap.
Those timing rows are preliminary. These checks do not support a 30% native
random or native greedy claim. See native.json for every sample and duration.

Local validation passes: cargo fmt, strict release workspace Clippy with all
targets/features, 130 default release test executions, and 136 all-feature
release test executions. Tests cover ordered enumeration, all transition branches,
invalid-choice atomicity, turn-limit atomicity, hidden-information boundaries,
replay and compile-time exclusive borrows. Normal core paths allocate zero times
in the allocation check. GitHub Actions was not used or changed.

See README.md for reproduction, BUILD.json for source hashes and compiler
settings, VALIDATION.json and logs for checks, and PLAN.md for hypotheses.
Executable and source hashes identify this uncommitted result. The screen
source_diff hashes describe the workspace during measurement, not necessarily
the frozen screen build; the core-only/buffer build stages are defined above.
