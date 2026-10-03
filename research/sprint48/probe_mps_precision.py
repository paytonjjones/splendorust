"""Bounded FP32 versus MPS autocast probe for the frozen refit Entity model.

This is an inference microbenchmark. It does not change the production service,
runtime, checkpoint, or game protocol. Run only when the MPS device is free.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import signal
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "research/architecture_pivots"))
sys.path.insert(0, str(ROOT / "research/e95"))
from flywheel_model import DTYPE  # noqa: E402
from models import forward, load  # noqa: E402


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def policy_distribution(logits: np.ndarray, mask: np.ndarray) -> np.ndarray:
    legal = mask > 0
    assert legal.any(axis=1).all()
    masked = np.where(legal, logits.astype(np.float64), -1.0e300)
    masked -= masked.max(axis=1, keepdims=True)
    probs = np.exp(masked)
    probs /= probs.sum(axis=1, keepdims=True)
    return probs


def validate_policy_distribution(probs: np.ndarray, mask: np.ndarray, mode: str) -> None:
    if not np.isfinite(probs).all():
        raise FloatingPointError(f"{mode} produced a non-finite policy probability")
    if np.max(np.abs(probs.sum(axis=1) - 1.0)) > 1e-6:
        raise FloatingPointError(f"{mode} legal policy probabilities do not sum to one")
    if np.any(probs[mask <= 0] != 0):
        raise FloatingPointError(f"{mode} assigned probability to an illegal action")


@torch.inference_mode()
def run_batch(model, packed: np.ndarray, mode: str) -> tuple[np.ndarray, dict]:
    # Match service transfers and the response copy. Entity inference uses only
    # x, but the current service also transfers its empty history and pool.
    batch = len(packed)
    host_history = np.zeros((batch, 16, 32), dtype="<f4")
    host_pool = np.zeros((batch, 90), dtype="<f4")
    resident_half = mode == "fp16_resident"
    input_dtype = torch.float16 if resident_half else torch.float32
    x = torch.from_numpy(np.ascontiguousarray(packed)).to("mps", dtype=input_dtype)
    history = torch.from_numpy(host_history).to("mps", dtype=input_dtype)
    pool = torch.from_numpy(host_pool).to("mps", dtype=input_dtype)
    enabled = mode == "fp16_autocast"
    with torch.autocast("mps", dtype=torch.float16, enabled=enabled):
        policy, value = forward(model, "entity", x, history, pool)[:2]
        output = torch.cat((policy, value), dim=-1).to("cpu").numpy().astype("<f4")
    expected_dtype = torch.float16 if enabled or resident_half else torch.float32
    if policy.dtype != expected_dtype or value.dtype != expected_dtype:
        raise TypeError(
            f"{mode} returned policy/value dtypes {policy.dtype}/{value.dtype}; "
            f"expected both {expected_dtype}"
        )
    if not np.isfinite(output).all():
        raise FloatingPointError(f"{mode} produced a non-finite output")
    return output, {
        "policy_dtype": str(policy.dtype),
        "value_dtype": str(value.dtype),
        "input_dtype": str(x.dtype),
        "model_dtype": str(next(model.parameters()).dtype),
    }


def synchronize() -> None:
    torch.mps.synchronize()


def measure(model, packed: np.ndarray, mode: str, warmups: int, repeats: int) -> dict:
    for _ in range(warmups):
        run_batch(model, packed, mode)
    synchronize()
    durations = []
    output = None
    output_dtype = None
    for _ in range(repeats):
        synchronize()
        started = time.perf_counter()
        output, output_dtype = run_batch(model, packed, mode)
        synchronize()
        durations.append(time.perf_counter() - started)
    assert output is not None and output_dtype is not None
    median = statistics.median(durations)
    return {
        "mode": mode,
        "batch_rows": len(packed),
        "warmup_batches": warmups,
        "timed_batches": repeats,
        "median_batch_seconds": median,
        "median_rows_per_second": len(packed) / median,
        "min_batch_seconds": min(durations),
        "max_batch_seconds": max(durations),
        "output_dtypes": output_dtype,
        "output": output,
    }


def timeout_handler(_signum, _frame):
    raise TimeoutError("probe exceeded its 50-second execution limit")


def run_probe(args, progress: dict) -> dict:
    autocast_available = torch.amp.autocast_mode.is_autocast_available("mps")
    if not autocast_available and not args.resident_fp16:
        raise RuntimeError("installed PyTorch does not provide MPS autocast")
    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS is not available; no CPU fallback is allowed")
    torch.set_num_threads(4)
    progress["phase"] = "input_validation"
    if sha(args.checkpoint) != "44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f":
        raise ValueError("checkpoint is not the frozen refit-01 model")
    registry = json.loads(args.registry.read_text())
    entry = next(item for item in registry["dev"] if item.get("native"))
    source = Path(entry["source"])
    packed_path = Path(entry["inputs"])
    if sha(source) != entry["source_sha256"] or sha(packed_path) != entry["inputs_sha256"]:
        raise ValueError("public development shard differs from its registry hashes")
    rows = np.memmap(source, mode="r", dtype=DTYPE)
    packed_rows = np.memmap(
        packed_path, mode="r", dtype="<f4", shape=(int(entry["rows"]), 525)
    )
    progress["phase"] = "model_load"
    model, payload = load(args.checkpoint, "mps")
    if payload.get("kind") != "entity":
        raise ValueError("checkpoint kind must be Entity")
    model.fast_tokenization = True
    resident_model = None
    if args.resident_fp16:
        progress["phase"] = "resident_fp16_model_copy"
        # Keep the FP32 model as the baseline. This copy holds resident FP16
        # weights; each measured call also sends all floating inputs as FP16.
        resident_model = copy.deepcopy(model).half().eval()
        if any(parameter.dtype != torch.float16 for parameter in resident_model.parameters()):
            raise TypeError("resident FP16 model copy contains a non-FP16 parameter")
        resident_model.fast_tokenization = True

    results = []
    for batch_size in (32, 64):
        progress.update(phase="measure", batch_size=batch_size)
        indexes = np.linspace(0, len(rows) - 1, batch_size, dtype=np.int64)
        packed = np.ascontiguousarray(packed_rows[indexes])
        mask = np.asarray(rows["mask"][indexes], dtype=np.float32)
        baseline = measure(model, packed, "fp32", args.warmups, args.repeats)
        progress["completed_fp32"] = {
            key: value for key, value in baseline.items() if key != "output"
        }
        base_output = baseline.pop("output")
        base_policy, base_value = base_output[:, :81], base_output[:, 81:]
        base_probs = policy_distribution(base_policy, mask)
        validate_policy_distribution(base_probs, mask, "fp32")
        result = {
            "batch_rows": batch_size,
            "fp32": baseline,
        }
        if autocast_available:
            progress["mode"] = "fp16_autocast"
            candidate = measure(model, packed, "fp16_autocast", args.warmups, args.repeats)
            progress.pop("mode")
            progress["completed_fp16_autocast"] = {
                key: value for key, value in candidate.items() if key != "output"
            }
            candidate_output = candidate.pop("output")
            half_policy, half_value = candidate_output[:, :81], candidate_output[:, 81:]
            half_probs = policy_distribution(half_policy, mask)
            validate_policy_distribution(half_probs, mask, "fp16_autocast")
            result.update(
                fp16_autocast=candidate,
                rows_per_second_ratio=candidate["median_rows_per_second"]
                / baseline["median_rows_per_second"],
                max_abs_policy_logit_error=float(np.max(np.abs(half_policy - base_policy))),
                max_abs_legal_policy_probability_error=float(
                    np.max(np.abs(half_probs - base_probs))
                ),
                max_abs_value_error=float(np.max(np.abs(half_value - base_value))),
            )
        if resident_model is not None:
            progress["mode"] = "fp16_resident"
            resident = measure(
                resident_model, packed, "fp16_resident", args.warmups, args.repeats
            )
            progress.pop("mode")
            progress["completed_fp16_resident"] = {
                key: value for key, value in resident.items() if key != "output"
            }
            resident_output = resident.pop("output")
            resident_policy, resident_value = resident_output[:, :81], resident_output[:, 81:]
            resident_probs = policy_distribution(resident_policy, mask)
            validate_policy_distribution(resident_probs, mask, "fp16_resident")
            result["fp16_resident"] = resident
            result["resident_rows_per_second_ratio"] = (
                resident["median_rows_per_second"] / baseline["median_rows_per_second"]
            )
            result["resident_max_abs_policy_logit_error"] = float(
                np.max(np.abs(resident_policy - base_policy))
            )
            result["resident_max_abs_legal_policy_probability_error"] = float(
                np.max(np.abs(resident_probs - base_probs))
            )
            result["resident_max_abs_value_error"] = float(
                np.max(np.abs(resident_value - base_value))
            )
            progress.pop("completed_fp16_resident")
        results.append(result)
        progress["completed_measurements"] = results
        progress.pop("completed_fp32")
        progress.pop("completed_fp16_autocast")

    result = {
        "schema": "mps-entity-precision-probe-v1",
        "status": "passed",
        "claim_scope": "inference microbenchmark only; no playing-strength result",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": sha(args.checkpoint),
        "checkpoint_kind": payload["kind"],
        "fast_entities": True,
        "source_public_dev": str(source),
        "source_sha256": entry["source_sha256"],
        "inputs_path": str(packed_path),
        "inputs_sha256": entry["inputs_sha256"],
        "selected_rows": "uniformly spaced rows from first registered native dev shard",
        "pytorch_version": torch.__version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "mps_built": torch.backends.mps.is_built(),
        "mps_available": torch.backends.mps.is_available(),
        "mps_autocast_available": autocast_available,
        "service_shape": "x plus zero history/pool transfers, then policy/value CPU copy",
        "code_sha256": {
            "models.py": sha(ROOT / "research/architecture_pivots/models.py"),
            "service.py": sha(ROOT / "research/architecture_pivots/service.py"),
            "runtime.py": sha(ROOT / "research/training_strategy/runtime.py"),
            "probe_mps_precision.py": sha(Path(__file__)),
        },
        "measurements": results,
    }
    if autocast_available:
        result["autocast_dtype"] = "torch.float16"
    if args.resident_fp16:
        result["resident_fp16"] = {
            "enabled": True,
            "method": "deepcopy Entity on MPS, cast model once with .half(), send x/history/pool as float16",
            "model_parameters_verified_float16": True,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "local/research/sprint48/refit-01/fit/model.pt",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "local/research/architecture-pivots/expanded-data.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--time-limit-seconds", type=int, default=50)
    parser.add_argument(
        "--resident-fp16",
        action="store_true",
        help="also measure an Entity copy with resident FP16 parameters and FP16 inputs",
    )
    args = parser.parse_args()
    if not 1 <= args.warmups <= 4 or not 2 <= args.repeats <= 12:
        parser.error("use 1-4 warmups and 2-12 timed batches")
    if not 10 <= args.time_limit_seconds <= 50:
        parser.error("time limit must be between 10 and 50 seconds")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(args.time_limit_seconds)
    progress = {"phase": "startup"}
    try:
        result = run_probe(args, progress)
        signal.alarm(0)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        partial = args.output.with_suffix(args.output.suffix + ".partial")
        partial.write_text(json.dumps(result, indent=2) + "\n")
        partial.replace(args.output)
        print(json.dumps(result, indent=2))
        return 0
    except BaseException as error:
        signal.alarm(0)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not args.output.exists():
            failure = {
                "schema": "mps-entity-precision-probe-v1",
                "status": "failed",
                "failure_type": type(error).__name__,
                "failure": str(error),
                "progress": progress,
                "checkpoint": str(args.checkpoint),
                "checkpoint_sha256": sha(args.checkpoint) if args.checkpoint.is_file() else None,
                "pytorch_version": torch.__version__,
                "python_version": sys.version,
                "platform": platform.platform(),
                "mps_autocast_available": torch.amp.autocast_mode.is_autocast_available("mps"),
            }
            args.output.write_text(json.dumps(failure, indent=2) + "\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
