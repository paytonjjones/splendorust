# Shared search environment integration

Imported evaluator9c354b6 in an isolated checkout and resolved it with the
current Gumbel and public-input paths. The same generic search kernel now
supports canonical and pinned AlphaZero-native rules. Root planning uses the
same operator in either environment. Canonical core rules remain unchanged.

Exact checks:934 legacy collector rows and910 noisy-Gumbel student-state rows
match the pre-integration bytes. Native PUCT matches the evaluator's frozen
worker at all1,448 decisions over16 games,including simulation/inference counts.
Frozen binary746bb15fb65a7ba4e74917c54cae65f171cacd2c1d10993c1f0aefa83d9184f7;
new binary f6fa67915b7e34533f33d484e32971aa936c1bce44cecb13a0906ff5cc197526.
Native Gumbel is legal,seed-repeatable,and uses the exact128 simulation budget.

Validation:112 release workspace tests,strictworkspaceClippy,and8 native
information tests passed. Differential validation matches pinned upstream at
9,204 positions and312,879 successor branches across100 complete games,
covering every native action encoding. A first6-game validation lacked two
encodings; that coverage failure is preserved. Parse/resolve and missing
validation-feature failures are also preserved and corrected.

Worker reset and Python schedules accept explicit search=puct or gumbel.
Default PUCT remains unchanged. Metadata records the selected search and
Gumbel parameters; upstream referee,800-simulation agent and information
asymmetry stay unchanged. Old artifacts retain their original frozen revision.
Public-context model inference derives extra fields from Observation only.
No strength claim comes from these execution and parity checks.

The active E74 job stayed in its original checkout throughout this work.
