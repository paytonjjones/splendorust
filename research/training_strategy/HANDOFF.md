# Closed Entity training study: next-agent handoff

Closed early at the user's request on 2026-10-03. The full registered study is
incomplete. Read RESULTS.md, CLOSED.json and FINAL_COST.json. Keep simpler
policy labels; no supported visit/Q/iterative adoption benefit was established.
The 256-game iterative check is exploratory and uncertain. No champion update.

Original worktree: /Users/payton.jones/.codex/worktrees/training-strategy/splendorust.
Baseline commit: 7367b05ea3a6587bf9c982756027652eeb974990.
Entity model SHA256: cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84.
CLOSED.json binds both selected generation-two weights and metrics.

## Restore

artifacts/INDEX.json lists each archive and exact manifest hash.
Run archive_results.py restore --archive ARCHIVE --output NEW_DIRECTORY
--manifest-sha256 HASH. Restore each archive into its own new directory.
Original location receipts move to data.original.json; run data.py on each
restored corpus to rebuild paths. The core archive has complete first-stage
work and explicitly incomplete second-stage provenance. All epochs, data,
interrupted work, resource pilots, frozen source and executables are retained.
archive-verification.json records actual restored byte and corpus checks.
Original source IDs refer to the frozen copy; main includes independent changes.
Keep original outputs immutable; use new directories and fresh runtime ports.

## Stopped and unrun

Chain-2 and the second controller were stopped on purpose. The frozen fit
finished all four epochs after its parent stopped; its exit code stays unknown.
The adopted collector has the same wait-status gap. The finite pilot and its
owned service stopped. The chat follow-up is deleted. Do not restart any chain,
babysitter, PCR or milestone without a new request.

The five planned second-generation 2,000-game screens, PCR and milestone/
20,000-game confirmation are unrun. If more work is funded, reuse the saved
fits and exact corpora. Check hashes and live process identities first.
Untouched planned masters 5461000000 through 5465000000 remain unused;
5492000000 was consumed by the exploratory run. Separate these records.
Resolve iterative versus static and frozen controls before adopting iterative
training. PCR/noise/staging/symmetry need their own controlled evidence.
HISTORY_HANDOFF.md and INTERIM_RESULTS.md are historical records; their live
process instructions do not authorize resumption.
