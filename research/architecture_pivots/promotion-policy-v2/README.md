# Promotion completion policy P2.1

The user requested this amendment on 2026-10-02 after seeing one no-action
game block the history/E81 screen. The first registration used 0.1%; the user
then requested more tolerance. `AMENDMENT.json` fixes the active limit at 1%
and preserves the initial registration's hash. These are amendments after a
known result, not advance registrations of that result.

Keep all original games, setups and rotations. Permit at most 1%
`no_legal_action` games per stage: 20 in a 2,000-game screen and 200 in a
20,000-game confirmation. No-action records have no winner. Unknown outcomes
get zero candidate credit for the existing lower confidence bound and one
for its upper bound. Thus, blocked games cannot help a candidate pass.
The denominator is all requested games. Reject decision-limit games,
excessive no-action counts, invalid evidence and execution errors. The 1%
completion cap is a fixed operational limit, not a confidence statement
about the population block rate. Report observed status counts separately.

The paired 95% interval, one-point promotion margin and fresh milestone seed
rules stay fixed. `scripts/promote.py` records the active policy and status
counts. Use `--max-no-action-fraction 0` to request the old strict behavior.
Do not skip blocked setups or replace them with fresh seeds. An identical
rerun can check reproducibility but adds no independent evidence. Changing
the agent to avoid blocks is a separate agent experiment.

Reassess a preserved run into a new file:

```sh
python3 scripts/reassess_promotion.py --input research/architecture_pivots/expanded-history-gate --output /tmp/history-p2.1-reassessment.json
```

The output path must not exist. The command checks the original raw and
record hashes, run settings, source, seed schedule and confidence interval.
It never edits the original report or decision and does not change the
champion. `reassess_all.py` covers every finished canonical architecture gate,
including negative results, and retains immutable per-run reassessments.

The retained history screen has 1,999 normal finishes and one no-action game.
Candidate credit is 59.05% with that unknown treated as a full loss, versus
59.08% among completed games. Its conservative lower bound is 54.76%, which
clears 51%. This is a passing screen under P2.1, not fresh confirmation.
The cold-small screen also stops failing solely for completion, but its
strength bound does not pass. E81 stays the champion.

The in-progress parent screen retains its old loaded gate. Only the waiting
attribution and canonical-confirmation controllers were resumed with the
new policy. Their original plans remain intact, with separate P2.1 receipts.
All checkpoints, search settings and seed streams remain fixed. The selected
milestone uses worst-case credit over all requested games, not conditional
credit among completed games.

Validation: 38 local Python tests pass, including rare no-action acceptance,
the cap boundary, strict mode, no invented winners, all-unknown bounds,
decision-limit rejection, fresh confirmation scheduling, error exits,
invalid arguments and immutable historical reassessment.
The real CLI completes a separate two-game screen and two-game confirmation
with frozen E81 against itself, records P2.1, and correctly retains the baseline.
Its checks include formatting, strict workspace Clippy and all 125 release
tests. This command check is not strength evidence. The first attempt lacked
the model environment variable; its failure is retained separately.
`VALIDATION.json` records the commands, hashes and observed results. The
original history screen is also retained as exact compressed raw bytes in
`evidence/`, with its original run manifest and decision.
