# Entity training strategy: provisional results

The study is incomplete. Matched-search canonical screens support a gain
from an offline one-hot pass and an offline visits pass. The two direct
comparisons do not support a benefit from visit targets or action-Q
supervision. Iterative learning and cap randomization remain untested for
strength. A major strength gain has not been established.

This draft describes evidence checked on 2026-10-03 UTC. The active experiment
settings remain those in `PREREGISTRATION.md`, `EFFICIENCY.md` and `MILESTONE.md`.
The frozen Entity checkpoint is unchanged, with SHA256
`cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84`.
The external AlphaZero target and official E81 champion are unchanged.

## Completed work

- Inspected the pinned upstream training/search code and frozen Entity handoff.
- Added root visits, explored-action Q, root value and terminal outcome targets,
  with a matched one-hot control and an optional Q output.
- Completed 64-game collection pilots at 4, 8, 16 and 32 workers. Targets,
  model inputs and ordered game histories are byte-identical across all four.
- Collected 2,000 training games and 400 separate development games. All games
  completed and replayed. Independent audits bind every terminal label to its
  retained game record and check legal/explored masks and Q conservation.
- Finished all three four-epoch fits from the same checkpoint. Each selected
  epoch 1 using the registered common development score.
- Finished all five first-stage 2,000-game canonical screens and checked
  their records, settings, hashes and model bindings. Four have all games
  complete; the Q/visits screen retains one unknown no-action outcome.
- Started the registered second generation using visits as the common
  research parent for iterative and frozen-teacher continuation.
- Archived and restored all 246 first-stage files. All saved bytes match;
  six restored corpora pass independent terminal-label checks. This includes
  interrupted outputs and the Q comparison's unknown outcome.
- Finished current-model generation-two collection: 2,000 complete, replayed
  games with no incomplete outcomes. The matched frozen-teacher control has
  finished with 1,999 complete games and one blocked game. The common 400-game
  development corpus is complete. Both passed independent label audits;
  the second-generation fits are running. Strength remains untested.

Training data contain 111,065 eligible targets; development data contain
22,283. Audit IDs are excluded from the public model inputs. See
`training-target-audit.json`, `development-target-audit.json` and
`first-stage-evidence.json` for hashes and measurements.

## Playing strength

The one-hot model scored **56.325% win credit** against original Entity over
2,000 complete games. The record-derived 95% interval is **52.03–60.62%**.
Both agents used canonical Gumbel128, depth16 and pool3, with 32 workers.
The fresh evaluation master was 5431000000. Shared wins receive split credit.

The visits model scored **56.05%**, with a 95% interval of **51.71–60.39%**,
at fresh master 5432000000. The visits-Q model scored **54.875%**, with a
95% interval of **50.57–59.18%**, at fresh master 5433000000. Both screens
completed all 2,000 games at the same search settings.

Onehot and visits pass the registered strict benefit threshold. Visits-Q does
not pass that threshold. All three point estimates are below the registered
60% major-gain threshold. Each result is conditional on its
opponent and search budget. It does not establish an external ranking.
All three fits share the same root/terminal value mixture. This first screen
measures a whole offline training pass; it does not isolate policy labels.
The direct visits/onehot screen scored **49.45%** visits credit, with a
95% interval of **45.21–53.69%**, over 2,000 complete games at fresh master
5434000000. It does not establish a benefit or a clear regression from visit
targets. Lower held-out visit loss did not establish a strength advantage.
The direct Q/visits screen scored **49.30–49.35%** Q-model credit, with a
95% interval of **45.02–53.63%**, at fresh master 5435000000. Of 2,000 requested
games, 1,999 completed and one stopped with `no_legal_action`. The unfinished
game has no winner or rank. Its unknown credit stays in the bounds; no capped
game occurred. It cannot pass the registered strict completion condition.
The result also does not establish a statistical benefit or clear regression
from Q supervision. Do not rank policy labels from the three separate
comparisons against original Entity.

| Question | Current evidence |
|---|---|
| Does the one-hot offline pass beat original Entity? | Supported by one fresh 2,000-game screen. |
| Does the visits offline pass beat original Entity? | Supported by one fresh 2,000-game screen. |
| Does the visits-Q offline pass beat original Entity by the registered margin? | Not established; its interval includes the 51% threshold. |
| Do visit targets beat one-hot targets? | Ambiguous: 49.45% credit, interval 45.21–53.69%. No supported benefit. |
| Does explored-action Q add strength? | Not supported: 49.30–49.35% credit, interval 45.02–53.63%, one unknown outcome. |
| Does iterative self-play beat frozen-teacher continuation? | Second-generation data are audited; fits running and strength tests pending. |
| Does cap randomization improve strength per generation cost? | Controlled study registered; not run. |
| Do staging, exploration or symmetry augmentation help? | Untested. |
| Is there a major strength gain? | Not established. |

## Held-out metrics

These are correlated position metrics on the development games. They are not
substitutes for playing strength. All values use the selected epoch.

| Fit | Visit CE | Terminal Brier | Explored-Q signed MSE |
|---|---:|---:|---:|
| Onehot | 1.51849 | 0.214967 | — |
| Visits | 1.42282 | 0.215073 | — |
| Visits-Q | 1.42502 | 0.214771 | 0.058522 |

The Q model's held-out pairwise Q-rank agreement is 62.16%. Visit loss is
lower for the soft-target fits; their strength advantage remains untested.
Full policy, value and Q metrics and exact checkpoint hashes are retained.

## Costs and interruption

| Completed stage | Shared-host wall time |
|---|---:|
| Training collection, 2,000 games | 2.463 hours |
| Development collection, 400 games | 35.5 minutes |
| Onehot / visits / visits-Q fit | 243.1 / 240.7 / 243.4 seconds |
| Onehot canonical screen, 2,000 games | 2.069 hours |
| Visits canonical screen, 2,000 games | 2.119 hours |
| Visits-Q canonical screen, 2,000 games | 2.040 hours |
| Visits / onehot direct screen, 2,000 games | 2.204 hours |
| Q / visits direct screen, 2,000 requested games | 2.263 hours |
| Current-model generation-two collection, 2,000 games | 2.204 hours |
| Frozen-teacher generation-two collection, 2,000 games | 2.412 hours |
| Common second-generation development, 400 games | 23.1 minutes |

Training collection used 26,751,234 model calls and 28,432,640 simulations.
The 32-worker pilot had 10.16 times the 4-worker throughput. Fixed 32-row
model batches waste rows when few games are active; both players also use
Entity search here. Changing host load prevents isolated attribution of the
whole scaling gain. `COLLECTION_COST.md` retains the workload comparison.

The original controller and first recovery stopped during the visits screen
without terminal receipts. Their processes were confirmed absent before
recovery. All interrupted files and service counters remain under the first
study directory. Their cost must be included in final accounting; interrupted
games are excluded from strength counts. The cause is not yet established.
Recovery 2 uses the saved checkpoints and the same registered seeds/settings.
It runs in a separate OS session so it can continue across chat updates.

Final inference/search costs and strength per compute remain incomplete.
No model has been promoted.

On the user's request for more Mac resources, excluded whole-game pilots
compared 32 and 64 workers with fixed 32-row GPU batches and unchanged weights.
Collection took 447.051 / 351.536 seconds; arena took 267.462 / 180.686 seconds.
Collection bytes and ordered arena records match exactly. These shared-host
measurements support 1.272 times collection throughput and 1.480 times arena
throughput, or 32.4% less arena wall time. They are scheduling evidence, not
strength evidence. `RESOURCE_AMENDMENT.md` records the permitted change.

The new development corpus and remaining strength screens use 64 workers.
Existing generation-two corpora and the live frozen collector keep their
32-worker setting; PCR generation keeps 32 to match its full control. The
new controller adopts the original collector without repeating its games.
Its original parent's wait status may be unavailable after the deliberate
handoff. That status remains unknown; the completed corpus must still pass
its replay and label audit. Pilot overhead remains part of total study cost.

The live frozen-teacher collection has retained one `no_legal_action` game
(game 1533). Its winner mask is zero and all 46 retained outcome labels are
NaN. None of these rows is eligible for training. Its 11,264 simulations and
11,302 model calls remain paid generation work. This follows the registered
finite-outcome training rule; it does not relax strict completion for strength
screens. `second-frozen-incomplete-observation.json` binds the partial record
and row evidence. The final corpus has 1,999 complete games, one no-action game
and no capped games; all histories replayed. `second-frozen-target-audit.json`
checks its 111,354 raw rows, 111,241 eligible rows, 46 excluded unknown-outcome
rows and 67 other excluded rows. `second-development-target-audit.json` checks
the common development corpus: 22,202 raw rows and 22,192 eligible rows.

## Completion and merge decision

Keep this report provisional and keep the study off `main` for now. Finish
the iterative-versus-frozen study and registered efficiency comparison.
Apply the registered fresh milestone
confirmation if required. Retain negative, ambiguous and untested results.
Close cost accounting, archive and restore-check all deliverables, and run
the local merge checks before a final results commit and merge decision.

`HANDOFF.md` contains the exact commands, recovery paths and remaining work.

## Interpretation for a training decision

The final recommendation must identify which specific training changes to
adopt, retain, reject or defer. Use the registered record-derived strength
thresholds and actual cost accounting for that decision:

- Prefer visit targets only if their direct comparison with one-hot supports
  a benefit. Lower visit loss alone is insufficient.
- Add action-Q supervision only if the direct Q/visits comparison supports
  its extra training cost. The Q output stays out of runtime search.
- Prefer iterative generation only if it improves on the static model and
  its matched frozen-teacher control. One second-generation gain does not
  prove continued improvement for unlimited generations.
- Prefer cap randomization if the direct matched-call comparison supports a
  strength benefit and its actual cost is practical. Faster collection alone
  does not justify adoption. Keep actual wall cost separate from the matched
  useful-call budget; an uncertain strength/cost trade-off needs further evidence.
- Report ambiguity as uncertainty and do not select a production recipe from
  a favorable point estimate alone. A research parent chosen by the registered
  fallback rule is not itself evidence that the component should be adopted.

At present, the supported direction is to continue testing search-enhanced
training updates. There is insufficient strength evidence to recommend soft
targets, Q supervision, iterative generation or cap randomization yet. The
direct visits/onehot screen gives no reason to adopt visit targets in
production. If research selection falls back to visits, that choice fixes
a common parent for the next experiment; it does not establish an advantage
over onehot. Visits was selected by that fallback rule for generation two.
The next experiment isolates the effect of changing the data-generating
teacher while both fits use the same parent, update count and 50/50 replay.
Generation two uses 2,000 new setups at master 5440000000 and a new common
400-game development corpus at 5450000000. Five fresh matched-search screens
will compare iterative and frozen continuation with the static parent, each
other and original Entity. Do not attribute any future gain to visit targets
from this teacher comparison.
