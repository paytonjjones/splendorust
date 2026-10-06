# Closed-study archive

The user closed the study early. The full registered experiment is incomplete.
artifacts/INDEX.json binds both archive manifests; archive-verification.json
records 867 restored core files, 72 restored closure files and nine corpus audits.
All archived bytes match. Selected and epoch checkpoints retain their exact
hashes. Original executables and source inputs are in the core archive.

Restore each archive into its own new directory through archive_results.py.
Pass the index manifest hash with --manifest-sha256. Original data receipts
move to data.original.json; run data.py for restored corpus paths. Executable
bytes are retained; set execute permission before running a restored executable.
The complete first stage uses a study label. The unfinished second stage and
closure logs use explicit provenance labels, without false completion receipts.

FINAL_COST.json retains actual command receipts, duplicate locations, reported
collector/fit time where parent wait status is unknown, and last logged service
counters. Counts exclude duplicate copied receipts. Service elapsed time is not
added to the commands it served. Missing interrupted cost tails remain unknown.
Core archive/restore command receipts are retained. The final closure pack and
restore were byte-checked but have no separate measured elapsed-time receipt;
that small cost is unmeasured, not zero. Shared-host elapsed time is not isolated
GPU time or FLOPs. Do not present the inventory as an exact total host cost.

The archived protocol and old handoff remain historical. No automated experiment
or chat follow-up should restart without a new user request.
