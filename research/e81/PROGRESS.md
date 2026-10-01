# E81 progress

The collector supports optional chosen-action teacher labels. Default actor behavior and sampling are unchanged. All 113 release tests and strict Clippy pass. A 16-game validation produces 880 legal one-hot rows; serial and parallel files match. All setups, inputs, masks and outcomes match the E74 prefix exactly. Default legacy collection remains byte-exact.

The first 1,000-game shard is complete: 55,572 positions, 178.97 seconds. Its setup/input/mask/outcome arrays match the original E74 shard exactly. Full collection, training and a fresh 2,000-game screen continue. No model selection or strength claim has been made.

The teacher is frozen E68 Gumbel800 with noise0, chosen-action labels, and a separate frozen E68 Gumbel128 actor. Five training shards and one development shard reuse the E74 setup/policy streams. The training architecture remains the fast bootstrap model. The registered fresh screen uses master4540000000. E56 remains the confirmed champion.
