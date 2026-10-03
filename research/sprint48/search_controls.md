# Sprint 48 search controls: preregistration

Status: controls are implemented in the worker and native runner. The campaign
owner must build and freeze the updated worker before using non-default values.
The chance-universe control is a separate search profile change. It has no
outcomes yet.
The initial baseline jobs used the pre-change worker and remain separate.

## Goal

Expose the native candidate's search settings so the campaign can test whether
more root coverage and a longer horizon improve play against the unchanged
AlphaZero800 target. Keep the current settings as exact defaults. Do not edit
AlphaZero source, settings, checkpoint, rules, or RNG handling.

This is a controls change, not a strength result. Every changed setting is a
new candidate profile and needs fresh seeds. The final run must use a frozen
worker path, model descriptor/checkpoint, service configuration, and settings.

## Current path

`native_policy_worker` accepts `reset(seed, iterations, depth, search,
root_only)`. It hard-codes three sampled worlds, Gumbel root cap 16, zero root
noise, PUCT `cpuct=0.4`, `fpu_reduction=0.02965`, and zero uniform prior.
`run.py` supplies depth but records worlds and Gumbel settings as constants.
`schedule.py` forwards only iterations, search, root-only, and model path. The
runner resolves the worker at `target/release/examples/native_policy_worker`.

Gumbel supports at most 81 legal root actions in its fixed arrays. A cap of
zero is invalid and can leave its active list empty. Depth zero is silently
clamped to one in search. A world pool of zero is valid and samples a fresh
world per simulation; positive values reuse that many sampled root worlds.
Native games stop at 124 turns. Trees are fresh at each real decision.

The native chance refill path differs from pinned AlphaZero. Native search
currently passes no seed and uses policy-RNG draws for every refill. The
upstream search selects one nonzero magic seed for each simulation, cycles its
three universes, and passes the same seed through every simulated transition.
The existing native draw path already implements the matching deterministic
refill formula when it receives a nonzero seed. This control tests whether that
chance coupling improves search quality. It does not change referee rules or
the sampled public-observation boundary.

## Small interface change

Add optional fields to `reset` with the current values as fallbacks:

- `world_pool`: default 3; accept 0 through 64.
- `gumbel_max_considered`: default 16; accept 1 through 81.
- `chance_universes`: default 0; accept 0 through 64. Zero must consume no
  extra policy-RNG values. Positive values draw nonzero seeds from policy RNG
  once per universe at each root search, use the same seed for every simulated
  transition in that simulation, and cycle by simulation index. When both
  `world_pool` and `chance_universes` are positive, both cycle by that index.
  Seeded refill is native-search-only; the canonical referee and its RNG do
  not change.
- `dynamic_fpu`: default false. When true, the existing dynamic FPU update
  averages newly visited values into a node value. The worker must echo this
  value; an old worker may omit it only when false is requested.
- Keep `depth` required for backward compatibility; validate 1 through 124.

Expose the same controls in `run.py` and `schedule.py` as `--world-pool`,
`--gumbel-max-considered`, `--chance-universes`, `--dynamic-fpu`, and the existing `--depth`.
Keep the current values as CLI defaults. Reject invalid ranges before starting
workers. The Gumbel cap
applies only to Gumbel; record it as null for PUCT so metadata does not imply
that PUCT uses it. Preserve the current behavior for all old commands.

Add optional `--policy-binary` to both scripts. Its default is the existing
`target/release/examples/native_policy_worker` path. Resolve and validate the
file once, then use that exact path for every shard. The baseline owner must
copy the first built worker to a campaign-owned frozen path before any rebuild.
Record the resolved path and SHA256 in each run's metadata and schedule plan.
Include binary path/hash and all search settings in cross-shard equality
checks. Keep source hashes and exact reproduction commands.

Also allow optional `--strength-binary` in run and schedule; its default stays
`target/release/examples/strength_worker`. Use the selected executable for the
upstream `data` RPC. Record its resolved path and SHA256 in each run and plan,
and require shard agreement. Replay uses the recorded path by default, accepts
an explicit override, and checks its SHA256 against run metadata. This binds
the native static-data source to the same frozen runtime as the game runner.

The reset request sends all settings explicitly, including defaults. The
worker sets them after constructing `NeuralAgent`. It returns the accepted
settings in the reset reply so the runner can fail if requested and active
settings differ. Only the candidate worker receives these settings. The
AlphaZero adapter remains unchanged.

## Identity and metadata

Keep the existing search algorithm names and record parameters separately:
`iterations`, `depth`, `world_pool`, `chance_universes`, `root_only`, and, for Gumbel,
`max_considered`, `cvisit=50`, `cscale=0.1`, and `root_noise=0`. Record
`policy_binary_path` and `policy_binary_sha256`. The core `source_id` does not
cover examples or Python. Bind the worker, `run.py`, and `schedule.py` with
explicit source SHA256 fields, and compiled workers with binary SHA256. Keep the pinned
AlphaZero source/checkpoint hashes and native profile fields unchanged.

## Targeted checks after the binary freeze

1. Compile the updated worker once into the campaign's selected build path,
   then copy and hash that binary before running it. Do not rebuild it during a
   schedule.
2. Send reset without the new fields and verify it accepts the original config:
   depth 16, pool 3, cap 16, noise 0, PUCT constants unchanged.
3. Send reset with non-default values and verify the reply and `choose` work
   counters. Check caps 1 and 81, pool 0 and 64, and depth 1 and 124. Check
   rejection of cap 0/82, pool 65, and depth 0/125.
4. Use a public observation and its exact legal set. Check the selected action
   is legal and remains independent of hidden deck/reservation identities.
   Use a multi-action root. Confirm exact simulation counts at budgets 0, 1,
   and a small positive count; the worker intentionally bypasses search when
   only one legal action exists.
5. Run a one-block dry invocation only if the campaign owner schedules it.
   Compare default reset/run output with the frozen baseline on the same fixture
   before claiming compatibility. Never use a final seed for this check.

Do not start a strength schedule or infer a playing gain from these checks.
