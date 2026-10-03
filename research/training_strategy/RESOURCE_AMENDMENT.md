# Resource scheduling amendment

The user requested more Mac resources on 2026-10-03. This permits scheduling
changes after whole-game parity and cost checks. It does not change the
research hypotheses, checkpoint selection, public inputs, training recipe,
setup or policy seeds, search simulations, depth, world pool or game counts.

The GPU inference service keeps its fixed 32-row arithmetic and exact weight
bytes. The resource pilots are excluded from training and strength evidence.
They reuse the excluded 64-game collection scaling setups at master
5401000000/policy 8401000000, and use 64 paired arena games at master 5491000000.
Compare 32 and 64 workers on the same service and retain shared-host load.
Require identical raw/input/history bytes for collection and identical ordered
arena records, including incomplete statuses and trajectory hashes. Apply
64-worker evaluation only if whole-game arena throughput improves by at
least 10%. Retain every timing and the original output hashes.

The completed generation-two current-model corpus and live frozen-teacher
collector keep their original 32 workers. Do not repeat these games to change
their worker count. The new development corpus and later strength screens
may use 64 workers after the parity check. Both training arms share this
development corpus and keep the same update count and optimizer settings.
PCR generation keeps 32 workers to match the full-generation collection
configuration. Both PCR pilots use that same worker count. Its strength
screens and a conditional milestone may use the approved 64-worker profile.

`run_iterative_resource.py` can adopt the live frozen collector after the
original controller is deliberately stopped. It waits for the existing
collector to finish and audits its saved corpus before continuing. It retains
the original plan, source hashes and service logs. If the original parent's
process wait status cannot be recovered, record that status as unknown;
never fabricate an exit code. The completed, replayed data and audit remain
required. No partial or incomplete corpus can be treated as complete.

The old stage chain must be stopped before this handoff. Save both controllers'
identities, source bytes and stop reason. A new chain validates the declared
resource amendment and pilot hash and waits for the adopted second stage.
Do not overwrite or reuse old chain/recovery directories. Record every
resource-pilot cost as additional study work. Collection and arena timing
remain shared-host measurements; this amendment supplies no strength claim.
