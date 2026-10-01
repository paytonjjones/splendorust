# E95 progress

The supervision pivot is implemented. E92 established weak external strength; E89 failed to compound and E93 rejected fixed-budget consensus. This experiment uses unchanged AlphaZero800 expert labels and public inputs at every node. See PREREGISTRATION.md for the fixed recipe and evaluation seeds.

The 28-game collection pilot takes49.08s with8 workers and34.55s with14 workers, including startup under shared host load. Native rows, context arrays and replay histories are exact across both settings. Two parallel one-game shards also reproduce the serial two-game corpus exactly. The full5,000-training/1,000-development schedule is active with14 workers; all data comes from disjoint fresh seeds.

The new model has143,470 parameters. It uses392 public mean features,120 membership marginals,7 reservation-context fields,1 public rules flag and5 padding zeros. The first spatial projection has75 rows; the remaining trunk and heads retain E81's structure. Added columns start at zero. All parameters will train. Canonical and native search use the same public representation at every node; the rules flag is explicit. Runtime receives no private identities or teacher state.

Initialization matches E81 on the mean input exactly in Python; checkpoint reload is exact. Rust inference agrees on108 positions within1.526e-5 logits and1.669e-6 policy/value. The Rust blind-reservation test establishes exact hidden-world prediction invariance and rules-flag behavior. Strict Clippy and all124 release workspace tests pass. Two old training corpora remain byte-exact. The old native E81 endpoint preserves128 actions, search counts and sampled feature records exactly. An initial compile error used the wrong core action API; its log is preserved with the repaired passing test.

Collection uses a frozen pre-change worker. It labels the teacher's executed action and selected-action Qsa, in contrast to E94's diagnostic root-average Q. Every complete shard must replay all transitions before it becomes training data. E94 and E92 are excluded. No trained result, promotion or external dominance claim yet.

After collection, finish.py trains the one registered recipe, checks native inference and decision cost, then runs separate fresh2,000-game canonical and external screens. The canonical champion stays unchanged. Raw arrays remain in local/research/e95; compressed histories and receipts will be preserved in this directory when collection completes.
