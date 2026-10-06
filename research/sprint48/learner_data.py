"""Relabel fixed learner-trajectory histories with the pinned AlphaZero teacher.

The input is a native schedule JSONL file. The learner actions stay fixed. The
script replays each selected paired setup, records only public learner inputs,
and queries a fresh privileged AlphaZero root for labels at learner turns.
Each invocation writes one training-compatible shard. Run separate invocations
with the same input and ``--workers N --worker-index i`` to split by setup block.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/strength/native"))
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "research/e86"))
sys.path.insert(0, str(ROOT / "research/e95"))
sys.path.insert(0, str(ROOT / "research/sprint48"))

from upstream import DEFAULT_STRENGTH_BINARY, PIN, Tracker, Upstream, sha, stream  # noqa: E402
from validate import RPC  # noqa: E402
from public_model import inputs as model_inputs  # noqa: E402
from flywheel_model import DTYPE  # noqa: E402
from evidence import summarize as summarize_evidence  # noqa: E402

PROFILE = "alphazero-native-32a27ac-v1"
TEACHER_CHECKPOINT_SHA256 = "6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07"
DEFAULT_POLICY_BINARY = ROOT / "target/release/examples/native_policy_worker"
FINAL_EXTERNAL_MASTER = json.loads((ROOT / "research/sprint48/PLAN.json").read_text())["seeds"]["final_external"]["master"]


def observation_context(observation: dict) -> np.ndarray:
    """Return E95's seven reservation fields from the actor's observation."""
    viewer = observation["viewer"]
    opponent = observation["players"][1 - viewer]
    context = np.zeros(7, dtype="<f4")
    for slot, reservation in enumerate(opponent["reserved"][:opponent["reserved_count"]]):
        if reservation["public"] is False:
            if reservation["card"] != 255:
                raise ValueError("opponent blind reservation identity leaked into observation")
            context[slot] = 1.0
        context[slot + 3] = (reservation["tier"] + 1) / 3
        context[6] += context[slot] / 3
    return context


def candidate_seat(record: dict) -> int:
    seats = record["seats"]
    if len(seats) != 2 or seats.count("champion") != 1:
        raise ValueError("record must contain one candidate seat and one AlphaZero seat")
    return seats.index("champion")


def candidate_credit(record: dict) -> float:
    if record.get("status") != "complete" or record.get("rewards") is None:
        raise ValueError("candidate outcome is unknown for an incomplete record")
    credit = float(record["rewards"][candidate_seat(record)])
    if not 0.0 <= credit <= 1.0:
        raise ValueError("candidate credit is outside [0,1]")
    return credit


def block_owner(block: int, workers: int) -> int:
    if workers < 1:
        raise ValueError("workers must be positive")
    return block % workers


def read_schedule(path: Path) -> tuple[dict, list[dict]]:
    with path.open() as source:
        lines = [line for line in source if line.strip()]
    if len(lines) < 2:
        raise ValueError("native schedule must contain metadata and game records")
    metadata = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:]]
    return metadata, records


def validate_schedule(metadata: dict, records: list[dict], learner_descriptor: Path) -> None:
    if metadata.get("engine") != "alphazero_native" or metadata.get("ruleset") != PROFILE:
        raise ValueError("input is not the registered native AlphaZero profile")
    if metadata.get("upstream_revision") != PIN:
        raise ValueError("input does not use the pinned AlphaZero source")
    if metadata.get("upstream_checkpoint_sha256") != TEACHER_CHECKPOINT_SHA256:
        raise ValueError("input AlphaZero checkpoint differs from the registered checkpoint")
    if metadata.get("external_config", {}).get("numMCTSSims") != 800:
        raise ValueError("AlphaZero must use its pinned 800-simulation search")
    if metadata.get("model_sha256") != sha(learner_descriptor):
        raise ValueError("schedule candidate descriptor differs from learner descriptor")
    if metadata.get("master") == FINAL_EXTERNAL_MASTER:
        raise ValueError("final external master is sealed and cannot be used for training data")
    if len(records) != metadata.get("games") or len(records) % 2:
        raise ValueError("schedule record count is incomplete")


def check_setup_id_disjoint(selected_ids: list[int] | set[int], excluded_ids: set[int]) -> None:
    selected_values = list(selected_ids)
    selected_set = set(selected_values)
    selected_low32 = {value % 2**32 for value in selected_values}
    excluded_low32 = {value % 2**32 for value in excluded_ids}
    if len(selected_low32) != len(selected_values):
        raise ValueError("selected setup IDs collide after native low-32-bit seeding")
    overlap = selected_set & excluded_ids
    low32_overlap = selected_low32 & excluded_low32
    if overlap or low32_overlap:
        raise ValueError(f"setup IDs overlap excluded data: exact={sorted(overlap)[:8]}, "
                         f"low32={sorted(low32_overlap)[:8]}")


def paired_blocks(records: list[dict], max_blocks: int) -> list[tuple[int, list[dict]]]:
    if max_blocks < 1:
        raise ValueError("max-blocks must be positive")
    grouped: dict[int, list[dict]] = {}
    for record in records:
        grouped.setdefault(int(record["block"]), []).append(record)
    result = []
    for block in sorted(grouped)[:max_blocks]:
        pair = sorted(grouped[block], key=lambda row: int(row["rotation"]))
        if len(pair) != 2 or [int(row["rotation"]) for row in pair] != [0, 1]:
            raise ValueError(f"block {block} does not contain both seat rotations")
        if pair[0]["setup_seed"] != pair[1]["setup_seed"]:
            raise ValueError(f"block {block} has different setup seeds across rotations")
        if pair[0]["initial_state"] != pair[1]["initial_state"]:
            raise ValueError(f"block {block} has different initial states across rotations")
        result.append((block, pair))
    return result


def read_setup_ids(path: Path | None) -> set[int]:
    if path is None:
        return set()
    return {int(line.strip()) for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def teacher_target(upstream: Upstream, state: np.ndarray, actor: int, turn: int,
                   seed: int, legal: list[int]) -> tuple[int, float]:
    """Query a fresh pinned teacher tree at this exact hidden state."""
    upstream.reset_policy(seed)
    canonical = upstream.game.getCanonicalForm(state, actor).copy()
    with upstream.torch.no_grad():
        probs, _, full = upstream.tree.getActionProb(
            canonical, temp=0.5 if turn + 1 <= 6 else 0.0, force_full_search=True)
    if not full:
        raise RuntimeError("pinned teacher did not complete full search")
    action = int(np.argmax(probs))
    if action not in legal:
        raise ValueError(f"teacher selected illegal action {action}")
    node = upstream.tree.nodes_data[upstream.game.stringRepresentation(canonical)]
    if node[5][action] <= 0:
        raise ValueError("teacher selected action has no completed root visit")
    q = float(node[4][action])
    if not np.isfinite(q) or not -1.0 <= q <= 1.0:
        raise ValueError("teacher selected-action root Q is invalid")
    return action, (q + 1.0) / 2.0


def sample_public_input(feature_rpc: RPC, observation: dict, context: np.ndarray,
                        sample_seed: int, native: bool = True) -> tuple[np.ndarray, np.ndarray]:
    sampled = feature_rpc.call(op="sample", observation=observation, seed=sample_seed)
    features = np.asarray(sampled["features"], dtype="<f4")
    if features.shape != (392,) or not np.isfinite(features).all():
        raise ValueError("public feature worker returned invalid features")
    packed = model_inputs(features[None, :], context[None, :], native)[0]
    if packed.shape != (525,) or not np.isfinite(packed).all():
        raise ValueError("public model input is invalid")
    return features, packed


def process_record(upstream: Upstream, feature_rpc: RPC, metadata: dict, record: dict,
                  feature_master: int, teacher_master: int, invariance_left: list[int],
                  label_rows: bool = True) -> tuple[list, list, list]:
    """Replay one record and return DTYPE rows, contexts, and public audit rows."""
    record_id = int(record["index"])
    block = int(record["block"])
    if int(record["setup_seed"]) != stream(metadata["master"], "setup", block):
        raise ValueError(f"record {record_id} setup seed does not match its stream")
    state = upstream.setup(int(record["setup_seed"]))
    if not np.array_equal(state, np.asarray(record["initial_state"], dtype=np.int8)):
        raise ValueError(f"record {record_id} initial state differs on replay")
    tracker = Tracker(upstream, state)
    actor = 0
    actions = record["actions"]
    chance_seeds = record["chance_seeds"]
    state_hashes = record["state_sha256"]
    observation_hashes = record["policy_observation_sha256"]
    if not (len(actions) == len(chance_seeds) == len(state_hashes) == len(observation_hashes)):
        raise ValueError(f"record {record_id} transition arrays have different lengths")
    learner = candidate_seat(record)
    rows, contexts, audit = [], [], []
    complete = record.get("status") == "complete"
    if complete:
        outcome = candidate_credit(record)
    else:
        outcome = None

    for turn, (actor_action, chance, state_digest, observation_digest) in enumerate(
            zip(actions, chance_seeds, state_hashes, observation_hashes)):
        if upstream.rewards(state, actor) is not None:
            raise ValueError(f"record {record_id} contains actions after terminal state")
        legal = upstream.legal(state, actor)
        actor_action = int(actor_action)
        if actor_action not in legal:
            raise ValueError(f"record {record_id} contains illegal action at turn {turn}")
        if int(chance) != stream(metadata["master"], "chance", block, turn):
            raise ValueError(f"record {record_id} chance seed differs at turn {turn}")

        is_learner = actor == learner
        if is_learner:
            observation = tracker.snapshot(state, actor)
            observation_hash = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()
            if observation_digest != observation_hash:
                raise ValueError(f"record {record_id} learner observation differs at turn {turn}")
            if complete and label_rows:
                context = observation_context(observation)
                features, packed = sample_public_input(
                    feature_rpc, observation, context,
                    stream(feature_master, "encoding", record_id, turn))
                if invariance_left[0] > 0:
                    baseline = packed
                    for repeat in range(1, 8):
                        _, other = sample_public_input(
                            feature_rpc, observation, context,
                            stream(feature_master, "encoding-view", record_id * 8 + turn, repeat))
                        if not np.array_equal(baseline, other):
                            raise ValueError("learner inputs changed across sampled hidden worlds")
                    invariance_left[0] -= 1
                row = np.zeros((), dtype=DTYPE)
                row["setup"] = int(record["setup_seed"])
                row["x"] = features
                row["mask"][legal] = 1.0
                target_action, teacher_value = teacher_target(
                    upstream, state, actor, int(observation["turns"]),
                    stream(teacher_master, "teacher", record_id, turn), legal)
                row["policy"][target_action] = 1.0
                row["teacher"] = teacher_value
                row["outcome"] = outcome
                rows.append(row)
                contexts.append(context)
                audit.append(dict(record_index=record_id, block=block, rotation=int(record["rotation"]),
                    turn=turn, setup_seed=int(record["setup_seed"]), actor=actor,
                    actor_action=actor_action, teacher_action=target_action,
                    teacher_credit=teacher_value, outcome_credit=outcome,
                    observation_sha256=observation_hash, public_inputs_sha256=hashlib.sha256(packed.tobytes()).hexdigest()))
        elif observation_digest is not None:
            raise ValueError(f"record {record_id} has an AlphaZero observation hash at turn {turn}")

        child, next_actor = upstream.apply(state, actor, actor_action, int(chance))
        tracker.update(state, child, actor, actor_action)
        state, actor = child, next_actor
        digest = hashlib.sha256(state.tobytes()).hexdigest()
        if digest != state_digest:
            raise ValueError(f"record {record_id} state hash differs after turn {turn}")

    if record.get("decisions") != len(actions) or record.get("turns") != len(actions):
        raise ValueError(f"record {record_id} decision counts differ")
    terminal = upstream.rewards(state, actor)
    if complete:
        if terminal is None or not np.allclose(record.get("native_rewards", []), terminal,
                                               rtol=0.0, atol=1e-12):
            raise ValueError(f"record {record_id} terminal rewards differ")
        winners = [i for i, reward in enumerate(terminal) if reward > 0]
        credits = [1.0 / len(winners) if i in winners else 0.0 for i in range(2)]
        if record.get("rewards") != credits:
            raise ValueError(f"record {record_id} recorded credit differs")
    elif terminal is not None or record.get("rewards") is not None:
        raise ValueError(f"record {record_id} incomplete status has terminal rewards")
    scores = [int(upstream.game.getScore(state, i)) for i in range(2)]
    if record.get("scores") != scores:
        raise ValueError(f"record {record_id} final scores differ")
    return rows, contexts, audit


def run(args: argparse.Namespace) -> dict:
    learner_descriptor = args.learner_descriptor.resolve(strict=True)
    source = args.input.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metadata, records = read_schedule(source)
    validate_schedule(metadata, records, learner_descriptor)
    source_evidence = summarize_evidence(metadata, records)
    blocks = paired_blocks(records, args.max_blocks)
    skip_ids = read_setup_ids(args.skip_setup_ids)
    candidate_blocks = blocks
    candidate_ids = {int(pair[0]["setup_seed"]) for _, pair in candidate_blocks}
    if not skip_ids <= candidate_ids:
        raise ValueError(f"skip setup IDs are absent from selected source blocks: {sorted(skip_ids - candidate_ids)[:8]}")
    selected = [(block, pair) for block, pair in blocks
                if block_owner(block, args.workers) == args.worker_index
                and int(pair[0]["setup_seed"]) not in skip_ids]
    if not selected:
        raise ValueError("this worker shard has no setup blocks")
    if len({metadata["master"], args.feature_master, args.teacher_master}) != 3:
        raise ValueError("input, feature, and teacher masters must be different")
    excluded = read_setup_ids(args.exclude_setup_ids)
    selected_ids = [int(pair[0]["setup_seed"]) for _, pair in selected]
    check_setup_id_disjoint(selected_ids, excluded)

    policy_binary = args.policy_binary.resolve(strict=True)
    strength_binary = args.strength_binary.resolve(strict=True)
    if metadata.get("policy_binary_sha256") and sha(policy_binary) != metadata["policy_binary_sha256"]:
        raise ValueError("policy binary differs from the binary used by the source schedule")
    if metadata.get("strength_binary_sha256") and sha(strength_binary) != metadata["strength_binary_sha256"]:
        raise ValueError("strength binary differs from the binary used by the source schedule")

    # The descriptor is only used by the public-observation sampling operation.
    # The learner's actions are fixed in the source history; AlphaZero acts only
    # as an offline labeler and receives the full referee state in memory.
    # Upstream may create temporary ONNX files in its current directory.
    with tempfile.TemporaryDirectory(prefix="sprint48-learner-data-") as temporary:
        import os
        old_cwd = Path.cwd()
        try:
            os.chdir(temporary)
            upstream = Upstream(network=True, strength_binary=strength_binary)
        finally:
            os.chdir(old_cwd)
    if upstream.data.get("source_id") != metadata.get("source_id"):
        raise ValueError("selected strength binary data identity differs from the source schedule")
    feature_rpc = RPC([policy_binary, learner_descriptor])
    all_rows, all_contexts, all_audit = [], [], []
    processed, complete_blocks, incomplete_blocks = [], 0, 0
    invariance_left = [args.invariance_checks]
    started = time.monotonic()
    try:
        for block, pair in selected:
            # The paired setup is one split unit. If either rotation is unknown,
            # replay both histories but do not train from either rotation.
            block_complete = all(record.get("status") == "complete" for record in pair)
            before = len(all_rows)
            for record in pair:
                rows, contexts, audit = process_record(upstream, feature_rpc, metadata, record,
                    args.feature_master, args.teacher_master, invariance_left, block_complete)
                all_rows.extend(rows); all_contexts.extend(contexts); all_audit.extend(audit)
                processed.append(dict(index=record["index"], block=block, rotation=record["rotation"],
                    status=record["status"], decisions=len(record["actions"])))
            if block_complete:
                complete_blocks += 1
            else:
                incomplete_blocks += 1
                del all_rows[before:]
                del all_contexts[before:]
                del all_audit[before:]
    finally:
        feature_rpc.close()

    if not all_rows:
        raise ValueError("selected complete blocks produced no learner rows")
    args.output.mkdir(parents=True, exist_ok=False)
    rows_array = np.asarray(all_rows, dtype=DTYPE)
    contexts_array = np.asarray(all_contexts, dtype="<f4")
    inputs_array = model_inputs(rows_array["x"], contexts_array, True).astype("<f4", copy=False)
    if len(rows_array) != len(contexts_array) or inputs_array.shape != (len(rows_array), 525):
        raise ValueError("training arrays have incompatible lengths or shapes")
    for key in ("x", "mask", "policy", "teacher", "outcome"):
        if not np.isfinite(rows_array[key]).all():
            raise ValueError(f"training column {key} contains a non-finite value")
    if not np.isfinite(contexts_array).all() or not np.isfinite(inputs_array).all():
        raise ValueError("packed training inputs contain a non-finite value")

    data_path = args.output / "data.bin"
    context_path = args.output / "data.context.bin"
    input_path = args.output / "data.inputs.bin"
    rows_array.tofile(data_path); contexts_array.tofile(context_path); inputs_array.tofile(input_path)
    setup_ids_path = args.output / "setup_ids.txt"
    setup_ids = sorted(int(value) for value in np.unique(rows_array["setup"]))
    setup_ids_path.write_text("".join(f"{value}\n" for value in setup_ids))
    with (args.output / "histories.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for item in all_audit:
                compressed.write((json.dumps(item, sort_keys=True) + "\n").encode())
    manifest = dict(schema="sprint48-learner-dagger-shard-v1", split=args.split,
        input=str(source), input_sha256=sha(source), input_master=metadata["master"],
        input_candidate_sha256=metadata["model_sha256"], learner_descriptor=str(learner_descriptor),
        learner_descriptor_sha256=sha(learner_descriptor), teacher_revision=PIN,
        teacher_checkpoint_sha256=TEACHER_CHECKPOINT_SHA256,
        teacher_config=dict(upstream.config), teacher_master=args.teacher_master,
        source_evidence=source_evidence,
        policy_binary=str(policy_binary), policy_binary_sha256=sha(policy_binary),
        strength_binary=str(strength_binary), strength_binary_sha256=sha(strength_binary),
        source_strength_hash_present=bool(metadata.get("strength_binary_sha256")),
        feature_master=args.feature_master, max_blocks=args.max_blocks,
        workers=args.workers, worker_index=args.worker_index, selected_blocks=[b for b, _ in selected],
        complete_blocks=complete_blocks, incomplete_blocks=incomplete_blocks,
        games=len(processed), rows=len(rows_array), unique_setup_ids=len(setup_ids),
        setup_ids_file=setup_ids_path.name, excluded_setup_ids_file=str(args.exclude_setup_ids) if args.exclude_setup_ids else None,
        excluded_setup_ids_sha256=sha(args.exclude_setup_ids) if args.exclude_setup_ids else None,
        skipped_setup_ids=sorted(skip_ids), skip_setup_ids_file=str(args.skip_setup_ids) if args.skip_setup_ids else None,
        label="one-hot pinned AlphaZero action; selected-action root Q credit; candidate terminal credit",
        learner_inputs="public native observation only; AlphaZero privileged state is label-only",
        public_world_invariance_checks=args.invariance_checks-invariance_left[0],
        source_profile=PROFILE, source_candidate_search=dict(iterations=metadata["iterations"],
            depth=metadata["depth"], search=metadata["search"], world_pool=metadata["world_pool"],
            root_only=metadata["root_only"], gumbel_config=metadata.get("gumbel_config")),
        processed_records=processed, audit_sha256=sha(args.output / "histories.jsonl.gz"),
        source_code_sha256=sha(Path(__file__)), seconds=time.monotonic()-started,
        files={p.name:sha(p) for p in (data_path, context_path, input_path, setup_ids_path)})
    manifest["registry_entry"] = dict(source=str(data_path.resolve()), source_sha256=manifest["files"][data_path.name],
        context=str(context_path.resolve()), context_sha256=manifest["files"][context_path.name],
        inputs=str(input_path.resolve()), inputs_sha256=manifest["files"][input_path.name],
        native=True, rows=len(rows_array), setups=manifest["unique_setup_ids"])
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="merged native schedule games.jsonl")
    parser.add_argument("--learner-descriptor", type=Path, required=True,
                        help="the exact .bin descriptor used by the source schedule")
    parser.add_argument("--policy-binary", type=Path, default=DEFAULT_POLICY_BINARY,
                        help="frozen native observation-feature worker binary")
    parser.add_argument("--strength-binary", type=Path, default=DEFAULT_STRENGTH_BINARY,
                        help="frozen AlphaZero reference-engine metadata binary")
    parser.add_argument("--output", type=Path, required=True, help="new shard directory")
    parser.add_argument("--split", choices=("train", "dev"), required=True)
    parser.add_argument("--max-blocks", type=int, required=True, help="finite number of leading paired setups")
    parser.add_argument("--workers", type=int, default=1, help="number of disjoint block shards")
    parser.add_argument("--worker-index", type=int, default=0, help="this shard's index in [0, workers)")
    parser.add_argument("--teacher-master", type=int, required=True, help="fresh teacher-search RNG stream")
    parser.add_argument("--feature-master", type=int, required=True, help="fresh public-world sampling RNG stream")
    parser.add_argument("--invariance-checks", type=int, default=32,
                        help="number of learner states checked across eight sampled hidden worlds")
    parser.add_argument("--exclude-setup-ids", type=Path, required=True,
                        help="text file of setup IDs already assigned to another split or corpus")
    parser.add_argument("--skip-setup-ids", type=Path,
                        help="text file of source setup IDs already labelled in this source")
    args = parser.parse_args(argv)
    if args.workers < 1 or not 0 <= args.worker_index < args.workers:
        parser.error("require 0 <= worker-index < workers")
    if args.max_blocks < 1 or args.invariance_checks < 0:
        parser.error("max-blocks must be positive and invariance-checks nonnegative")
    return args


def main(argv: list[str] | None = None) -> None:
    result = run(parse_args(argv))
    print(json.dumps({k: result[k] for k in ("split", "games", "rows", "complete_blocks",
                                               "incomplete_blocks", "files", "seconds")}, indent=2))


if __name__ == "__main__":
    main()
