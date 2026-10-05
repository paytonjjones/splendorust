# AhinLendor source, weights, and search audit

## Result

The isolated upstream checkout is pinned to commit
`96e6f2daff83147495826c4a2073dc3c9c856cc9` (2026-07-25). Its Git worktree is
clean. The documented flagship weights are **not present** in this checkout,
and I found no public release or download path. This blocks a faithful
head-to-head strength benchmark against the flagship checkpoint. Do not use
random, freshly initialized, or locally trained substitute weights and label
them AhinLendor's flagship.

Evidence checked:

- No `.pt`, `.pth`, `.onnx`, or other model-weight file exists in the checkout
  or Git tree. `nn/checkpoints.py` loads a local checkpoint path; it does not
  define a download location.
- The repository has no Git tags. The official GitHub Releases page says
  there are no releases: [AhinLendor releases](https://github.com/inhabae/AhinLendor/releases).
- A bounded public registry search found no AhinLendor flagship model on
  Hugging Face or ModelScope. The project site did not expose a documented
  checkpoint download link.
- The README gives the search description and M2 timing, but no weight URL or
  checkpoint filename. The upstream `.gitignore` excludes `*.pt`.
- The README says “MIT License”, but the pinned tree has no `LICENSE` or
  `COPYING` file. This audit does not copy upstream source or binaries into
  tracked project files.

The public upstream claims that the later Spendee agent used 250,000 MCTS
simulations, 20,000 bootstrap simulations per legal root action, batch64 leaf
inference, and about 20 seconds per move on an M2. These are README claims,
not measurements reproduced here. See the
[pinned README](https://github.com/inhabae/AhinLendor/blob/96e6f2daff83147495826c4a2073dc3c9c856cc9/README.md#L39-L108).

## What the code supports

The compiled extension reports 90 standard cards, 10 standard nobles, 69
policy actions, and 252 state features. A reset smoke check returned 30 legal
start actions. The search API accepts a fixed simulation count and a leaf
evaluation batch size. Python `MCTSConfig` defaults to batch32; the Spendee
CLI accepts an explicit `--eval-batch-size 64`. Its `--gpu-batching-enabled`
shortcut selects batch32, so that flag alone does not match the documented
batch64 setting. The Python evaluator sends each batch to a PyTorch model on a
caller-selected device. No model inference was run on MPS.

The Spendee CLI exposes the documented search shape:

```text
--search-type mcts_bootstrap
--num-simulations 250000
--bootstrap-simulations-per-action 20000
--eval-batch-size 64
```

`run_bootstrap_mcts_search` shares one MCTS session. It forces each legal root
action for the first phase, then runs ordinary search on the same session.
Its `session_target` is `num_simulations + bootstrap_simulations_per_action
* legal_action_count`. Thus `250000` means 250,000 ordinary simulations plus
the bootstrap work; the exact total varies by position. The upstream source
implements this mode in `spendee/engine_policy.py:646-706`; the CLI fields are
in `spendee/cli.py:37-66`. The C++ session accepts the forced-root-action
filter and batch size in `py_splendor.cpp:1300-1384`.

Search is bounded by simulation count, not wall time. I found no per-move
deadline or time-budget API in the MCTS wrapper. The README's M2 figure does
not establish a 20-second limit on this M4 Pro. A future timed benchmark must
measure the actual checkpoint first and add a safe caller-side deadline if
needed. Do not assume that 250,000 plus bootstrap fits 20 seconds.

## Hidden information and adapter boundary

The extension exposes `NativeEnv.export_state()`, which includes exact deck
card IDs and all reservation IDs. The adapter must **not** pass a referee's
omniscient internal export to AhinLendor. Build the root payload from the
acting player's public observation, its own reserved-card IDs, public cards,
and public card counts. It is legal to reconstruct the multiset of unseen
cards from the public base deck after removing known public cards and the
acting player's own reservations. Do not give the true order of future draws
or the identities of the opponent's hidden reservations.

Upstream has an `ISMCTS` entry point. It shuffles hidden opponent reservations
with the remaining tier deck at each simulation and keys search nodes by the
acting player's information state (`native_mcts.cpp:706-763, 1020-1108`). The
Spendee adapter also has `ShadowState` and root-determinization code. The
flagship bootstrap wrapper instead calls the standard MCTS session on a
determinized root (`engine_policy.py:646-706`). This is safe only if the
adapter supplies a sanitized public payload. The existing Spendee observer
path is not yet a proof that a new SplendoRust referee adapter preserves the
same boundary; verify it with hidden-reservation and future-deck sentinels.

A native one-simulation CPU ISMCTS callback smoke test passed on the initial
state. It verifies the compiled interface and returned action-array shape;
it does not validate belief construction or strength.

## Local build

The pinned Python is
`local/strength/inference/bin/python` (CPython 3.11.13; PyTorch 2.5.1). It has
no importable `pybind11` package, and this host has no `cmake` executable.
PyTorch includes usable pybind11 headers, so the extension builds directly
with Apple clang++ 21 in optimized CPU mode. Run
`local/strength/inference/bin/python research/ahinlendor/external/build.py`.
The helper checks the upstream commit and source hashes, writes the ignored
extension to `local/strength/external/ahinlendor/`, runs CPU smoke checks, and
records the command and results:
[build-receipt.json](external/build-receipt.json).

Built extension SHA256:
`db31352c79b5dbce964d7a56c127e8f33a34d2604d25f97eb1a88e8db417aa8c`.
It reports `BUILD_TYPE=Release` and `BUILD_OPTIMIZED=true`. Import, card and
noble inventory, reset/legal-action, and one CPU ISMCTS simulation passed.
No upstream tracked file changed. No game match, MPS search, or model
inference ran. The upstream checkout has no tracked test suite in this
revision, so these are interface smoke checks only.

## Next gate

Wait for a checkpoint supplied by the user or documented by a public project
source. Do not contact the author. Until then, continue only with the
neutral-engine and observation-boundary work. After a checkpoint is
available, reproduce the intended hidden-information setup, measure search
time and batch behavior on this Mac, then run the mandated paired screen
under SplendoRust's neutral referee.
