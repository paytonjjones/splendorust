# Public reservation context

E69 proved that the transferred input omitted whether an opponent reservation
was public and its retained tier. E70 adds seven fields from Observation only:
unknown flags[3], present (tier+1)/3[3], and unknown count/3. The first projection
expands from 56 to 57 rows with 56 zero weights. Other layers stay unchanged.
The native SPINFO57 format carries depth and context width. Old models retain
their original path. No rule, RNG, replay, or engine version changes.

All seven saved-data sidecars were reconstructed with frozen actors in 477.90s.
Every setup, encoded input, legal mask, and outcome matched the original bytes;
teacher targets remain unchanged. Receipts identify original and context hashes.
The original corpus remains in local/research; the reconstruction command,
source, manifests, and receipts are preserved here.

Validation: 103 release workspace tests and strict workspace Clippy passed.
Python tests: 64 run, 35 passed, 29 optional-reference tests skipped.
Initialization is exact in Python and Rust. Checkpoint reload is exact; context
weights receive gradients; invalid payloads fail. PyTorch/native fixture error
is below the existing tolerance. Sixteen checked native games completed.
Both default and context-enabled collection reproduce the prior 934 rows byte
for byte. Collected context matches reconstruction exactly.

Fixed-fixture native inference cost ratio was 1.0194 (context/legacy), alternating
legacy/context/legacy, 3x10k calls each. Shared-host timing is descriptive.
The collector, trainer, diagnostic and restartable runner support context data;
SPINFO57 warm starts enable it automatically. Other student architectures and
incumbent distillation are rejected explicitly for this format.

Failed Clippy attempts are preserved. The faults were nested conditional syntax
and constant-size chunk APIs in validation code; all were corrected before the
final checks. See ../e71/REPORT.md for the matched strength experiment.
