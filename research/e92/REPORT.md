# E92: current champion against unchanged AlphaZero

E81 Gumbel128 scores 27.325% against unchanged AlphaZero800. All 2,000 paired native-profile games complete. The conservative 95% interval is 23.0303–31.6197%; the paired bootstrap interval is 25.425–29.3%. All 111,034 transitions pass native replay. This endpoint remains weak against the critical external target.

The E81 model hash is e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8. It is the canonical champion from CHAMPION.json. Native inference uses Gumbel128/depth16, three sampled worlds and noise0. AlphaZero remains at its pinned weights, 800 simulations, cpuct0.8, fpu0.0593 and three universes. SplendoRust receives public observations; AlphaZero retains its native private-information advantage. No canonical, equal-information, equal-compute or global ranking follows.

The frozen E56 PUCT128 confirmation was 23.395%. E92 is a separate model/search endpoint on fresh seeds; the point difference is 3.93 percentage points. Do not pool schedules or call that difference an isolated training gain. The upper bound well below 50% meets E92's preregistered pivot condition.

Eight native interface tests, all-feature release tests, and 100-game differential checks pass. The differential check covers 9,204 positions and 312,879 legal branch successors. The eight-worker schedule took 817.81 seconds under shared-host load. Exact raw archives, model/source/checkpoint/runtime hashes, commands and replay evidence are saved.

The driver retained a post-run frozen-input assertion failure: cargo test rebuilt two example workers after the initial preflight receipt. All source files, model weights, upstream files and settings stayed unchanged. Every actual arena shard records the same post-test policy binary SHA 5f6ff7995822a645ecaea4479743f3d9ac208dd8283d04345a79dc00fae5e90a. completion-audit.json verifies that endpoint and the actual current binary; both native tests and the full differential check were repeated on it. The original preflight hashes and failed driver log remain. No failed or partial game was counted.

Decision: pivot supervision toward the stronger external teacher and a deterministic public belief representation, while retaining fresh canonical checks. Repeated distillation of the weaker transferred lineage has not delivered dominance. E94's data-boundary pilot is separate from these held-out evaluation games. No E92 arena record may enter training or checkpoint selection. E81 stays the canonical champion until a new canonical promotion passes.
