# Sprint 48 value-target and backup audit

Read-only code audit. No game, build, GPU inference, or training ran for this
audit. The refit was active during the audit. This report does not claim a
strength gain.

## Findings

I found no player-perspective or sign reversal in the teacher labels, native
Entity inputs, or search backup path.

- `research/sprint48/learner_data.py:145-164` canonicalizes each state to the
  acting player before it queries the pinned AlphaZero tree. It reads Q for
  the selected root action and maps signed Q `[-1,1]` to acting-player credit
  `[0,1]`. The code requires a completed search, a legal selected action, and
  a visited root edge. The row is emitted only on the candidate's turn
  (`learner_data.py:222-247`), so this acting-player value is also the
  candidate-player value.
- `research/sprint48/learner_data.py:56-69,198-203,266-274` indexes terminal
  credit by the candidate seat, verifies replayed signed terminal rewards,
  and checks that the stored credit vector matches the winners. Paired seat
  rotations are checked at `learner_data.py:119-134`. Historical target audits
  report complete replay and legal labels: `research/e95/train-audit.log`
  reports 280,710 rows, mean selected-teacher credit 0.50868, and mean
  terminal credit 0.5. This is corpus validation, not strength evidence.
- Entity training uses `target = 2 * ((teacher_credit + outcome_credit) / 2)
  - 1`, then fits head 0 to that signed credit and head 1 to its negative
  (`research/architecture_pivots/train.py:138-152`). The two values in
  `EntityTransformer` are tanh outputs (`research/architecture_pivots/models.py:125-142,155-161`).
  The runtime reads the current player's output for search. Native features put
  the current player first (`crates/splendor-agents/src/native_environment.rs:547-559`),
  and `native_world_leaf` selects head 0 when the viewer is the current player
  (`crates/splendor-agents/src/neural_search.rs:679-733`). Native search calls
  evaluate on observations for the state’s current actor
  (`neural_search.rs:572-586`; `environment.rs:103-124`).
- This search backs up absolute player credits, so it does not need AlphaZero's
  scalar sign flip at each turn. At a leaf, it writes current-player credit
  into the current seat and the complement into the other seat
  (`neural_search.rs:572-586`). After recursion, a parent adds the returned
  credit for its own actor (`neural_search.rs:651-668`). The native trait maps
  signed terminal rewards to credits (`environment.rs:115-117`). This is
  equivalent in perspective to the pinned teacher's canonical `np_roll` at
  every transition (`local/strength/external/alphazero/MCTS.py:117-123,163-179`),
  but uses an explicit two-seat vector rather than a sign change.
- The native/canonical flag is set in input column 519 by
  `research/e95/public_model.py:22-28`; `train.py:45-57,65-93` sets it from
  the registered source profile. At runtime, public bootstrap models with
  75-row inputs require public context (`transfer.rs:517-522`), then
  `infer_with_history` forwards the native flag to `infer_with_profile`
  (`transfer.rs:590-602`). That path writes the flag into column 519
  (`transfer.rs:540-550`).
- Noble slot order is retained for native public models. Upstream schedules
  retain the initial native noble order (`benchmarks/strength/native/upstream.py:108-116,131-153`).
  Native feature construction maps each slot through its noble ID
  (`native_environment.rs:536-559`). Runtime dispatch chooses this order for
  public 75-row bootstrap models and keeps sorted order for legacy transferred
  models (`transfer.rs:509-516`; `neural_search.rs:688-692`). The focused test
  `public_native_leaf_preserves_teacher_noble_order` checks that path
  (`neural_search.rs:1344-1379`). Do not apply generic noble permutations to
  this fixed dataset or model contract.

## Concrete mismatch and limits

There is one small terminal-value mismatch for a shared win. Native rules give
both players signed reward `+0.01` (`native_environment.rs:468-488`), and the
search environment converts that to credit `0.505` for each seat
(`environment.rs:115-117`). The training corpus records shared winners as
`0.5` credit each (`learner_data.py:271-274`; `benchmarks/strength/native/finalize.py:45`).
This mismatch is limited to shared terminal wins and is small. It is not
evidence that more search will fail. Do not alter the active run; a later
change can map a shared native terminal result to exactly `0.5` per seat and
verify replay/search tests.

There is also a diagnostic gap, not a confirmed implementation error: the
current trainer selects checkpoints by policy cross-entropy plus four times
terminal-outcome Brier, not by teacher-Q calibration
(`research/architecture_pivots/train.py:186-198,231-244`). A prior canonical
search-target audit found root-network MSE 0.0143 and terminal Brier 0.1971
for the teacher root versus 0.2135 for the network on 22,192 positions
(`research/training_strategy/second-development-target-audit.json:41-43`).
That audit is canonical and position-weighted. It does not diagnose the current
native candidate. For a future registered branch, record native dev
teacher-Q error and selected-action Q rank alongside the existing selector;
keep the preregistered selector fixed for this refit.

No evidence here supports a claim that perspective handling caused the
45.7% exploratory screen. That screen is small, and the existing first-stage
native dev sample showed weaker policy fit for the one-hot candidate while
outcome Brier was slightly better (`research/sprint48/TRAINING_DIAGNOSTIC.md`).
