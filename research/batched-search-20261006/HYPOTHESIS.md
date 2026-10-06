# Batched PUCT exploratory hypothesis

Date: 2026-10-06

## Hypothesis

A batch-8 PUCT mode that queues eight observation-only leaf evaluations per search wave can raise single-game leaf-inference throughput by about 6x. It will use provisional visits during selection and apply the same leaf results and backups after the batch returns. Search simulations, legal action sets, observations, model weights, and all non-batch search settings stay fixed. The sequential mode remains the default. The batched mode is useful only if its paired win-credit difference versus sequential PUCT is no worse than -5 percentage points and complete-game cost improves materially. The screen is exploratory and cannot establish non-inferiority if its interval is wide.

## Fixed comparison

- Candidate: frozen Entity `SPENTY01` public-profile model from `research/STRENGTH_CHAMPION.json`.
- Control: current sequential PUCT implementation with the same model.
- Search: 6,400 simulations, depth 64, world pool 3, chance universes 3, dynamic FPU enabled, same native rules and public observation boundary.
- Change: batch size 8, with virtual visits while leaf requests are pending. No batching across independent games counts as a single-game optimization.
- Opponent: pinned AlphaZero800 under the registered native rules profile.
- Paired screen: 8 fresh setup seeds, both seats, and both Entity variants: 32 total games and 16 exact same-seed/same-seat variant pairs against AlphaZero800. Each pair holds seed, Entity seat, opponent seat, and opponent fixed while changing only sequential versus batched PUCT. Preserve unknown outcomes.
- Decision margin: -5 percentage points in batched-minus-sequential paired win credit. Report the paired interval; a quick wide interval is inconclusive.
- Cost report: measured leaf evaluations/second, complete-search time, and complete-game time. Do not equate model-only throughput with search or game throughput.
- Candidate order effect: if multiple traces reach one unresolved information state in the same wave, the first queued prediction is the frozen expansion value for all such traces. Later rows are counted as duplicate inference work. Sequential PUCT can descend after expanding the first trace, so this is an intentional order effect, not sequential equivalence.

## Finite resource budget and sequence

- 150 active minutes total for source work, validation, one non-outcome throughput pilot, one fixed paired screen, replay, and reporting. This cap was raised before the strength screen after the pilot showed a credible concurrent-service path within the budget.
- One GPU job at a time. GPU work is on hold until the parent releases its browser smoke-test slot.
- First inspect the traversal and model interfaces. Implement only if a true single-search leaf queue fits this budget and preserves the default path.
- Run a two-game batch-8 runtime pilot only to estimate execution cost; do not use its outcome for candidate selection or the paired result. A scalar cost pilot may stop incomplete if one-worker service cost is too high; retain partial counts and use the planned concurrent-service screen for the control cost.
- Keep the 16-pair screen fixed before launching its first game. If the measured pilot shows it cannot finish within the budget, stop before paired outcomes and report the reason; do not shrink the sample after seeing outcomes.

## Evidence limits

This is a small exploratory screen. Its sample is not sized to prove a five-point non-inferiority margin. A favorable point estimate with a wide interval does not establish strength parity. No champion change is authorized by this screen.
