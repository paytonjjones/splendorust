# Stopped batch-search test

The user stopped this test on 2026-10-06. Keep all saved records. The fixed
32-game sample did not finish, so it supports no strength decision.
See [STOPPED.json](STOPPED.json) for the saved and missing game counts.

Both versions used the same Entity weights through a native PyTorch/MPS
service. One version queued eight leaves; the other requested one leaf at a
time. Each used 6,400 simulations against pinned AlphaZero800. This was not a
WebGPU test or a direct match between the two search versions.

The shared service used a fixed batch of 32, including padding. Combined
service throughput did not establish sequential search progress or a sound
finish-time estimate. Earlier time estimates were not supported.

The raw pilot and partial screen files are retained unchanged. The frozen
plan identifies the source and binary used by that run. The complete batch-8
pilot has a replay receipt. Do not select a winner from this incomplete test.

[CANDIDATE.patch](CANDIDATE.patch) preserves the unmerged code for review.
It also includes the owner's later time-limit draft, which has not been
compiled or tested. The isolated worktree is retained. No part of this patch
is in the browser deployment. The deployed browser keeps sequential search.

The proposed smaller follow-up is a direct four-game match with two fresh
setups and both seat orders, using the same weights and five seconds per move.
It has not started. It can check a large regression; it cannot establish a
five-percentage-point strength margin.
