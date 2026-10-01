# AlphaZero-native environment plan

Date: 2026-09-30. Base: d9d4e4d. Worktree: 90ce/splendorust.
Branch: codex/alphazero-native-environment.

The user replaced the initial canonical-opponent adaptation objective before
any benchmark ran. The new objective adapts SplendoRust to the unchanged
AlphaZero native environment. No canonical-adapter results exist.

Hypothesis: a reusable environment interface can separate observation,
action, transition and reward semantics from the existing policy/value model
and information-set PUCT. The same frozen E56 model and search can then play
canonical rules or the pinned AlphaZero-native rules. Differential legal-set,
transition and terminal checks must pass before external comparison.

Keep the canonical engine/version, default agent configuration and main learning
loop unchanged. Preserve the existing diagnostic adapter and raw results.
Upstream AlphaZero revision 32a27ac1f85d5de2766cc5f60c2bf04e557f7836,
checkpoint, native rules and MCTS settings remain unchanged.
Use its own referee for the external benchmark, with reproducible setup copies
for full seat rotation and independent setup/chance/policy streams.
SplendoRust receives acting-player information only; sample private identities
from public history. Never pass native deck bitfields, opponent blind cards,
setup seed or referee RNG to its search.

Develop on fresh 40-game smoke schedule at master 4100000000. Freeze settings
before a 2,000-game screen at 4110000000, then a 20,000-game milestone at
4120000000. Main model: E56 SHA055c427ad1da9f86f1632e43409cb1648b7f8a350109d7d105ac5eae56f2df41,
128 simulations, depth16, three independent sampled worlds. External:
800 simulations, fpu0.0593, cpuct0.8, three upstream chance universes.
Do not tune settings on win rates. Record all raw histories, sources, model
hashes, stream definitions, commands and runtimes. All terminal rewards are
upstream rewards; distinguish win credit from signed native search rewards.
Retain incomplete records as unknown. Validate every recorded game by replay.
Report setup-block confidence intervals and fixed-budget limits. Do not claim
equal compute or a global/canonical strength rank from this native profile.

Pre-freeze encoder correction: Native rule fixtures preserve the native random
noble slot order. The confirmed SplendoRust encoder sorts noble IDs, so its
native model-input translation must retain that same sort. The initial 40-game
smoke and interrupted 1-process scaling trial used native slot order directly;
they are kept in development-native-slot-order* and are not benchmark evidence.
No opponent setting or weight is changed. Freeze after a shared-feature test.

Pre-register an exploratory higher-compute control before the screen outcomes:
2,000 paired games at master4150000000, same frozen E56 model, 800 SplendoRust
simulations, depth16, same unchanged AlphaZero800 and information boundary.
This tests added search compute, not a training gain or equal-compute claim.
Keep it separate from the 128-simulation 20,000-game primary endpoint.
