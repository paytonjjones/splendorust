"""Fit branch two with a fixed 90% base and 10% learner-label loss."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "research/e95"))
sys.path.insert(0, str(ROOT / "research/architecture_pivots"))
from flywheel_model import DTYPE, check_rows, sha  # noqa: E402
from models import create, forward, load  # noqa: E402

PARENT_SHA256 = "44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f"
SEED = 800000031
DAGGER_SEED = 0xDA66E2
BATCH = 512
DAGGER_ROWS_PER_UPDATE = 57
EPOCHS = 2


def checked_entries(entries: list[dict], label: str) -> list[tuple[np.memmap, np.memmap, bool]]:
    result = []
    seen_setup_ids: set[int] = set()
    for index, entry in enumerate(entries):
        for field in ("source", "context", "inputs"):
            path = Path(entry[field]).resolve(strict=True)
            expected = entry[field + "_sha256"]
            if sha(path) != expected:
                raise ValueError(f"{label} {index} {field} hash differs: {path}")
        rows = np.memmap(entry["source"], mode="r", dtype=DTYPE)
        inputs = np.memmap(entry["inputs"], mode="r", dtype="<f4",
                           shape=(int(entry["rows"]), 525))
        if len(rows) != int(entry["rows"]):
            raise ValueError(f"{label} {index} row count differs")
        check_rows(rows)
        if not np.isfinite(rows["outcome"]).all() or not np.isfinite(inputs).all():
            raise ValueError(f"{label} {index} has non-finite values")
        ids = set(map(int, np.unique(rows["setup"])))
        if ids & seen_setup_ids:
            raise ValueError(f"{label} setup IDs repeat across shards")
        seen_setup_ids |= ids
        if not isinstance(entry.get("native"), bool):
            raise ValueError(f"{label} has an invalid native flag")
        result.append((rows, inputs, bool(entry["native"])))
    if not result:
        raise ValueError(f"{label} has no data entries")
    return result


def load_registry(path: Path) -> tuple[dict, dict[str, list[dict]]]:
    value = json.loads(path.read_text())
    if value.get("schema") != "sprint48-dagger-branch2-registry-v1":
        raise ValueError("wrong branch-two registry schema")
    groups = value.get("groups")
    if not isinstance(groups, dict):
        raise ValueError("branch-two registry has no groups")
    expected = {"base_train", "base_dev", "dagger_train", "dagger_dev"}
    if set(groups) != expected:
        raise ValueError(f"branch-two groups must be exactly {sorted(expected)}")
    if any(not isinstance(groups[name], list) or not groups[name] for name in expected):
        raise ValueError("branch-two registry has an empty group")
    return value, groups


class DaggerSampler:
    """Uniformly sample DAgger rows across all registered shards."""

    def __init__(self, groups: list[tuple[np.memmap, np.memmap, bool]]):
        self.groups = groups
        self.ends = np.cumsum([len(rows) for rows, _, _ in groups], dtype=np.int64)
        self.total = int(self.ends[-1])
        if self.total <= 0:
            raise ValueError("DAgger training set is empty")

    def sample(self, count: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        global_rows = rng.integers(0, self.total, size=count, endpoint=False)
        rows = np.empty(count, dtype=DTYPE)
        inputs = np.empty((count, 525), dtype="<f4")
        starts = np.concatenate(([0], self.ends[:-1]))
        group_ids = np.searchsorted(self.ends, global_rows, side="right")
        for group_id, (source, packed, _) in enumerate(self.groups):
            positions = np.flatnonzero(group_ids == group_id)
            if len(positions):
                local_ids = global_rows[positions] - starts[group_id]
                rows[positions] = source[local_ids]
                inputs[positions] = packed[local_ids]
        return rows, inputs


def supervised_terms(result, mask: torch.Tensor, policy: torch.Tensor,
                     teacher: torch.Tensor, outcome: torch.Tensor
                     ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    logits, values = result[:2]
    logp = logits.masked_fill(mask == 0, -1e9).log_softmax(-1)
    target = torch.where(torch.isfinite(teacher), (teacher + outcome) / 2, outcome) * 2 - 1
    policy_term = -(policy * logp).sum(-1)
    value_term = ((values[:, 0] - target) ** 2 + (values[:, 1] + target) ** 2) / 2
    return policy_term + value_term, logp, values


def weighted_mix_loss(per_row: torch.Tensor, base_count: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    if base_count <= 0 or base_count >= len(per_row):
        raise ValueError("mixture needs non-empty base and DAgger rows")
    base_loss = per_row[:base_count].mean()
    dagger_loss = per_row[base_count:].mean()
    return 0.90 * base_loss + 0.10 * dagger_loss, base_loss, dagger_loss


def as_tensors(rows: np.ndarray, packed: np.ndarray, device: str):
    copy_rows = np.array(rows, copy=True)
    copy_packed = np.array(packed, copy=True)
    input_tensor = torch.from_numpy(copy_packed).to(device)
    targets = tuple(torch.from_numpy(np.array(copy_rows[name], copy=True)).to(device)
                    for name in ("mask", "policy", "teacher", "outcome"))
    return input_tensor, *targets


def evaluate_group(model, entries, device: str) -> dict:
    totals = np.zeros(9, dtype=np.float64)
    model.eval()
    with torch.no_grad():
        for rows, packed, _ in entries:
            for start in range(0, len(rows), BATCH):
                batch_rows = rows[start:start + BATCH]
                batch_inputs = packed[start:start + BATCH]
                input_tensor, mask, policy, teacher, outcome = as_tensors(batch_rows, batch_inputs, device)
                result = forward(model, "entity", input_tensor)
                _, logp, values = supervised_terms(result, mask, policy, teacher, outcome)
                probability = (values[:, 0] + 1) / 2
                target = torch.where(torch.isfinite(teacher), (teacher + outcome) / 2, outcome)
                valid_teacher = torch.isfinite(teacher)
                count = len(batch_rows)
                totals[0] += -(policy * logp).sum().item()
                totals[1] += (logp.argmax(-1) == policy.argmax(-1)).sum().item()
                totals[2] += ((probability - outcome) ** 2).sum().item()
                totals[3] += ((probability - target) ** 2).sum().item()
                totals[4] += count
                totals[5] += valid_teacher.sum().item()
                if valid_teacher.any():
                    q_error = probability[valid_teacher] - teacher[valid_teacher]
                    totals[6] += (q_error ** 2).sum().item()
                    totals[7] += q_error.abs().sum().item()
                totals[8] += 1
    if totals[4] == 0:
        raise ValueError("cannot evaluate an empty group")
    metrics = dict(policy_ce=totals[0] / totals[4],
        policy_accuracy=totals[1] / totals[4], outcome_brier=totals[2] / totals[4],
        target_brier=totals[3] / totals[4], rows=int(totals[4]),
        selection_score=(totals[0] + 4 * totals[2]) / totals[4],
        teacher_q_rows=int(totals[5]))
    if totals[5]:
        metrics["teacher_q_brier"] = totals[6] / totals[5]
        metrics["teacher_q_mae"] = totals[7] / totals[5]
    return metrics


def evaluate(model, base_dev, dagger_dev, device: str) -> dict:
    by_rule = {"native": [], "canonical": []}
    for entry in base_dev:
        by_rule["native" if entry[2] else "canonical"].append(entry)
    full_dev = {}
    full_ce = full_outcome_brier = full_rows = 0.0
    for name in ("native", "canonical"):
        if not by_rule[name]:
            raise ValueError(f"full dev has no {name} group")
        metrics = evaluate_group(model, by_rule[name], device)
        full_dev[name] = metrics
        full_ce += metrics["policy_ce"] * metrics["rows"]
        full_outcome_brier += metrics["outcome_brier"] * metrics["rows"]
        full_rows += metrics["rows"]
    full_score = (full_ce + 4 * full_outcome_brier) / full_rows
    dagger_metrics = evaluate_group(model, dagger_dev, device)
    score = 0.90 * full_score + 0.10 * dagger_metrics["selection_score"]
    return dict(full_dev=full_dev, full_dev_rows=int(full_rows),
        full_dev_score=full_score, dagger_dev=dagger_metrics,
        dagger_dev_score=dagger_metrics["selection_score"], selection_score=score,
        selection_rule="0.90 * existing full-dev (CE + 4 outcome Brier) + 0.10 * DAgger-dev (CE + 4 outcome Brier)")


def train(args: argparse.Namespace) -> int:
    if args.epochs != EPOCHS or args.batch != BATCH or args.dagger_rows != DAGGER_ROWS_PER_UPDATE:
        raise ValueError("branch two requires two epochs, batch 512, and 57 DAgger rows per update")
    if sha(args.parent) != PARENT_SHA256:
        raise ValueError("parent checkpoint is not the frozen refit-01 selection")
    if not args.output.exists():
        raise FileNotFoundError(f"output directory must be prepared by the wrapper: {args.output}")
    started = time.monotonic()
    registry, group_entries = load_registry(args.registry)
    base_train = checked_entries(group_entries["base_train"], "base train")
    base_dev = checked_entries(group_entries["base_dev"], "base dev")
    dagger_train = checked_entries(group_entries["dagger_train"], "DAgger train")
    dagger_dev = checked_entries(group_entries["dagger_dev"], "DAgger dev")
    sampler = DaggerSampler(dagger_train)

    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True, warn_only=True)
    base_rng = np.random.default_rng(SEED)
    dagger_rng = np.random.default_rng(DAGGER_SEED)
    parent, payload = load(args.parent)
    if payload.get("kind") != "entity" or payload.get("fast_entities") is not True:
        raise ValueError("frozen parent must be the selected fast-tokenized Entity checkpoint")
    model = create("entity").to(args.device)
    model.fast_tokenization = True
    model.load_state_dict(parent.state_dict(), strict=True)
    model.train()

    lr = 1e-4
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, EPOCHS, eta_min=lr / 10)
    updates_per_epoch = sum(math.ceil(len(rows) / BATCH) for rows, _, _ in base_train)
    base_rows_per_epoch = sum(len(rows) for rows, _, _ in base_train)
    manifest = dict(schema="sprint48-dagger-branch2-fit-v1", status="running",
        parent=str(args.parent), parent_sha256=sha(args.parent),
        registry=str(args.registry), registry_sha256=sha(args.registry),
        registry_data=registry, kind="entity", seed=SEED, dagger_seed=DAGGER_SEED,
        epochs=EPOCHS, batch=BATCH, dagger_rows_per_update=DAGGER_ROWS_PER_UPDATE,
        mixture=dict(base_loss_weight=0.90, dagger_loss_weight=0.10,
                     dagger_sampling="uniform over all registered train label rows, with replacement"),
        optimizer="fresh AdamW", learning_rate=lr, weight_decay=1e-4,
        scheduler="CosineAnnealingLR over 2 epochs; eta_min=1e-5", device=args.device,
        fast_entities=True, base_updates_per_epoch=updates_per_epoch,
        base_rows_per_epoch=base_rows_per_epoch,
        dagger_rows_per_epoch=updates_per_epoch * DAGGER_ROWS_PER_UPDATE,
        initial=None, history=[], selected_epoch=0, selected_score=None,
        code_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                     [Path(__file__), ROOT / "research/architecture_pivots/models.py",
                      ROOT / "research/flywheel_model.py", ROOT / "research/e95/public_model.py"]},
        parent_checkpoint_sha256=PARENT_SHA256)

    initial = evaluate(model, base_dev, dagger_dev, args.device)
    manifest["initial"] = initial
    manifest["selected_score"] = initial["selection_score"]
    manifest["selected_epoch"] = 0
    shutil.copyfile(args.parent, args.output / "model.pt")
    shutil.copyfile(args.parent, args.output / "latest.pt")
    manifest["selected_model_sha256"] = sha(args.output / "model.pt")
    manifest["latest_sha256"] = sha(args.output / "latest.pt")
    manifest["checkpoint_hashes"] = {"epoch_0": sha(args.output / "model.pt")}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(dict(stage="initial", **initial)), flush=True)

    for epoch in range(1, EPOCHS + 1):
        model.train()
        epoch_started = time.monotonic()
        base_losses = dagger_losses = 0.0
        base_rows_seen = dagger_rows_seen = updates = 0
        for group_index in base_rng.permutation(len(base_train)):
            rows, packed, _ = base_train[int(group_index)]
            order = base_rng.permutation(len(rows))
            for start in range(0, len(order), BATCH):
                selected = order[start:start + BATCH]
                base_batch = rows[selected]
                base_inputs = packed[selected]
                dagger_batch, dagger_inputs = sampler.sample(DAGGER_ROWS_PER_UPDATE, dagger_rng)
                joint_rows = np.concatenate((base_batch, dagger_batch))
                joint_inputs = np.concatenate((base_inputs, dagger_inputs), axis=0)
                input_tensor, mask, policy, teacher, outcome = as_tensors(
                    joint_rows, joint_inputs, args.device)
                result = forward(model, "entity", input_tensor)
                terms, _, _ = supervised_terms(result, mask, policy, teacher, outcome)
                loss, base_loss, dagger_loss = weighted_mix_loss(terms, len(base_batch))
                if not torch.isfinite(loss):
                    raise ValueError("non-finite mixed loss")
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                gradient_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                if not torch.isfinite(gradient_norm):
                    raise ValueError("non-finite gradient")
                optimizer.step()
                base_losses += base_loss.item()
                dagger_losses += dagger_loss.item()
                base_rows_seen += len(base_batch)
                dagger_rows_seen += len(dagger_batch)
                updates += 1
        if updates != updates_per_epoch or base_rows_seen != base_rows_per_epoch:
            raise AssertionError("base exposures or optimizer-step count changed")
        if dagger_rows_seen != updates_per_epoch * DAGGER_ROWS_PER_UPDATE:
            raise AssertionError("DAgger sample count differs from fixed mixture")
        schedule.step()
        epoch_metrics = evaluate(model, base_dev, dagger_dev, args.device)
        epoch_metrics.update(epoch=epoch, optimizer_updates=updates,
            base_rows_seen=base_rows_seen, dagger_rows_seen=dagger_rows_seen,
            mean_base_loss=base_losses / updates, mean_dagger_loss=dagger_losses / updates,
            epoch_seconds=time.monotonic() - epoch_started,
            seconds=time.monotonic() - started)
        manifest["history"].append(epoch_metrics)
        epoch_path = args.output / f"epoch-{epoch:02d}.pt"
        torch.save(dict(kind="entity", epoch=epoch, seed=SEED,
            history_ablation="full", fast_entities=True,
            state_dict={key: value.detach().cpu() for key, value in model.state_dict().items()}),
            epoch_path)
        shutil.copyfile(epoch_path, args.output / "latest.pt")
        if epoch_metrics["selection_score"] < manifest["selected_score"]:
            shutil.copyfile(epoch_path, args.output / "model.pt")
            manifest["selected_score"] = epoch_metrics["selection_score"]
            manifest["selected_epoch"] = epoch
        manifest["checkpoint_hashes"][f"epoch_{epoch}"] = sha(epoch_path)
        manifest["selected_model_sha256"] = sha(args.output / "model.pt")
        manifest["latest_sha256"] = sha(args.output / "latest.pt")
        manifest["seconds"] = time.monotonic() - started
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(epoch_metrics), flush=True)

    manifest["status"] = "complete"
    manifest["finished_seconds"] = time.monotonic() - started
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch", type=int, default=BATCH)
    parser.add_argument("--dagger-rows", type=int, default=DAGGER_ROWS_PER_UPDATE)
    parser.add_argument("--device", choices=("mps", "cpu"), default="mps")
    raise SystemExit(train(parser.parse_args()))


if __name__ == "__main__":
    main()
