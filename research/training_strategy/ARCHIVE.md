# Final archive checks

The first-stage archive and restore are verified. The full study is still open.
Do not pack a live study or classify a controller stop as a completed experiment.

The final archive must contain all completed stage directories. The pack command
now preserves every regular file, including profile text, frozen source files
and interrupted partial outputs. It rejects source symlinks and checks each
source hash again after compression. The existing first-stage archive is valid;
its inventory contained no files excluded by the former suffix filter.

Before final packing, copy the evidence outside these stage directories into a
new provenance directory. Retain original names and paths in a copy manifest.
Include both chain directories, all launch receipts and controller logs, the
resource pilot receipts, status snapshots, frozen source copies, final cost
receipts, archive verification receipts and final reports. Preserve all unknown
process exit statuses. Do not make a false `complete.json` for this evidence.
Use `--provenance label:directory` with the ordinary `--study` arguments.
Provenance labels are explicit in the archive manifest and do not assert study
completion. Do not archive the archive itself or its restored copies.

After packing, compare the complete source inventory with the manifest. Restore
into a new directory using the saved manifest SHA256. Check all file bytes,
checkpoint hashes, row and input hashes, and independent corpus label audits.
The restored `data.original.json` files retain original absolute paths; only the
location-dependent data receipts are rebuilt. Original launch commands and
incomplete records remain unchanged.

Copied receipts can occur in two locations. Final cost accounting must count
each actual command once and retain the receipt locations. Do not add collection
time to its command wrapper time, or service time to the commands it served, as
if these were separate wall costs. Report service work counters separately.
Incomplete command times stay unknown unless a retained observation supplies a
lower bound. Shared-host elapsed time does not establish isolated GPU cost.
Resource pilots and interrupted work remain additional paid study work, even
when excluded from training and strength counts.

`collect_costs.py` inventories actual command exits and last logged service
counters. It counts identical copied receipts once, rejects conflicting copied
exits, and retains missing exit codes as unknown. For an adopted collector with
no parent exit receipt, its completed corpus time is reported separately.
It does not assert corpus validity or full study completion. A provisional
inventory is saved at `local/research/training-strategy/cost-inventory-provisional.json`.
Rebuild the final inventory after the remaining studies finish:

```sh
local/strength/inference/bin/python research/training_strategy/collect_costs.py --directory local/research/training-strategy/first --directory local/research/training-strategy/second --directory local/research/training-strategy/efficiency --directory local/research/training-strategy/milestone --output local/research/training-strategy/cost-inventory-final.json
```

The inventory alone does not close costs. Add archive/restore receipts, retained
interruption observations, the common versus per-arm training cost allocation,
and the actual strength intervals. Keep unknown cost tails explicit.

Four archive tests cover nonstandard files, interrupted bytes, separate
provenance, missing study completion, and corrupt compressed chunks. These tests
do not replace the final archive and restore check on the actual study data.
