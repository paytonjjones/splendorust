"""Matched Entity label arms, with recent replay and a fixed update budget."""
import argparse
import json
import math
import sys
import time
from pathlib import Path
import numpy as np
import torch
from data import ROOT, prepare, sha

sys.path.insert(0, str(ROOT / 'research/architecture_pivots'))
from models import create, load


def policy_loss(logits, mask, target):
    logp = logits.masked_fill(mask == 0, -1e9).log_softmax(-1)
    return -(target * logp).sum(-1), logp


def value_target(root, outcome):
    return ((outcome * 2 - 1) + .837 * (root * 2 - 1)) / 1.837


def q_loss(prediction, q, explored):
    target = torch.nan_to_num(q) * 2 - 1
    errors = (prediction - target).square() * explored
    return errors.sum(-1) / explored.sum(-1).clamp_min(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', choices=('onehot', 'visits', 'visits-q'), required=True)
    ap.add_argument('--parent', type=Path, default=ROOT / 'research/entity_baseline/model.pt')
    ap.add_argument('--train', type=Path, action='append', required=True)
    ap.add_argument('--dev', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--batch', type=int, default=512)
    ap.add_argument('--epoch-rows', type=int, help='Fixed rows per epoch, split equally across replay generations')
    ap.add_argument('--seed', type=int, default=800000041)
    ap.add_argument('--device', choices=('cpu', 'mps'), default='mps')
    args = ap.parse_args()
    assert args.epochs > 0 and args.batch > 0
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    rng = np.random.default_rng(args.seed)
    training = [prepare(p) for p in args.train]
    dev = prepare(args.dev)
    train_ids = set().union(*(set(r['setup']) for r, _, _, _ in training))
    assert not train_ids & set(dev[0]['setup']), 'Train and development setups overlap'
    for i, (r, _, ix, _) in enumerate(training):
        assert len(ix) > 0
        for r2, _, _, _ in training[:i]:
            assert not set(r['setup']) & set(r2['setup']), 'Replay generations share setups'
    kind = 'entity-q' if args.arm == 'visits-q' else 'entity'
    model = create(kind)
    parent, payload = load(args.parent)
    assert payload['kind'] in ('entity', 'entity-q')
    state = {k: v for k, v in parent.state_dict().items() if kind == 'entity-q' or not k.startswith('action_q.')}
    missing, unexpected = model.load_state_dict(state, strict=False)
    assert not unexpected and all(k.startswith('action_q.') for k in missing)
    model.fast_tokenization = True
    model.to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, args.epochs, eta_min=1e-5)
    epoch_rows = args.epoch_rows or sum(len(ix) for _, _, ix, _ in training)
    assert epoch_rows > 0 and (len(training) == 1 or args.epoch_rows is not None)
    plan = dict(schema='matched-entity-supervision-fit-v1', arm=args.arm, kind=kind,
        seed=args.seed, parent_sha256=sha(args.parent), parent=str(args.parent),
        train=[e for _, _, _, e in training], dev=dev[3], epochs=args.epochs,
        batch=args.batch, epoch_rows=epoch_rows, optimizer='AdamW', learning_rate=1e-4,
        weight_decay=1e-4, minimum_lr=1e-5, gradient_limit=5, device=args.device,
        parameters=sum(p.numel() for p in model.parameters()),
        value_target='(Z_signed + .837 * root_signed) / 1.837', q_weight=int(args.arm == 'visits-q'),
        selection='visit CE +4 terminal Brier; identical criterion for all arms',
        scripts={str(Path(p).relative_to(ROOT)): sha(p) for p in [Path(__file__), Path(__file__).with_name('data.py'), ROOT/'research/architecture_pivots/models.py']})
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')

    def batch(data, ix):
        r, x = data[0][ix], data[1][ix]
        visits = r['visits'].astype(np.float32)
        policy = visits / visits.sum(-1, keepdims=True)
        arrays = [x, r['mask'], policy, r['root'], r['outcome'], r['q'], r['visits'] > 0]
        tensors = [torch.from_numpy(np.array(v, copy=True)).to(args.device) for v in arrays]
        return (*tensors, torch.from_numpy(r['action'].astype(np.int64)).to(args.device))

    def evaluate():
        model.eval()
        sums = np.zeros(12, dtype=np.float64)
        with torch.inference_mode():
            for begin in range(0, len(dev[2]), args.batch):
                x, mask, visits, root, outcome, q, explored, action = batch(dev, dev[2][begin:begin+args.batch])
                result = model(x)
                ce, logp = policy_loss(result[0], mask, visits)
                onehot_ce = -logp.gather(1, action[:, None]).squeeze(1)
                entropy = -(visits * visits.clamp_min(1e-30).log()).sum(-1)
                values = result[1][:, 0]
                n = len(x)
                sums[:9] += [ce.sum().item(), onehot_ce.sum().item(), entropy.sum().item(),
                    (logp.argmax(-1) == action).sum().item(),
                    (logp.argmax(-1) == visits.argmax(-1)).sum().item(),
                    (((values + 1)/2 - outcome).square()).sum().item(),
                    (values - value_target(root, outcome)).square().sum().item(),
                    (values - (root * 2 - 1)).square().sum().item(), n]
                if len(result) == 3:
                    sums[9] += q_loss(result[2], q, explored).sum().item()
                    # Pairwise rank agreement, excluding unknown and tied teacher values.
                    truth = torch.nan_to_num(q)
                    td = truth[:, :, None] - truth[:, None, :]
                    pd = result[2][:, :, None] - result[2][:, None, :]
                    pairs = explored[:, :, None] & explored[:, None, :] & (td > 1e-6)
                    sums[10] += ((pd > 0) & pairs).sum().item()
                    sums[11] += pairs.sum().item()
        n = sums[8]
        assert n > 0
        metrics = dict(visit_ce=sums[0]/n, onehot_ce=sums[1]/n,
            visit_kl=(sums[0]-sums[2])/n, target_entropy=sums[2]/n,
            executed_accuracy=sums[3]/n, visit_argmax_accuracy=sums[4]/n,
            terminal_brier=sums[5]/n, mixed_value_mse=sums[6]/n, root_value_mse=sums[7]/n,
            rows=int(n), selection_score=(sums[0]+4*sums[5])/n)
        if kind == 'entity-q':
            metrics.update(q_signed_mse=sums[9]/n, q_rank_agreement=sums[10]/max(1,sums[11]), q_rank_pairs=int(sums[11]))
        assert all(math.isfinite(v) for v in metrics.values())
        return metrics

    history = []
    initial = evaluate()
    (args.output / 'initial.json').write_text(json.dumps(initial, indent=2) + '\n')
    best = float('inf')
    best_epoch = None
    for epoch in range(1, args.epochs+1):
        model.train()
        order = []
        for group, (_, _, eligible, _) in enumerate(training):
            count = epoch_rows // len(training) + int(group < epoch_rows % len(training))
            if len(training) == 1 and count == len(eligible):
                indices = rng.permutation(eligible)
            else:
                indices = rng.choice(eligible, count, replace=count > len(eligible))
            order.extend((group, int(i)) for i in indices)
        rng.shuffle(order)
        total_loss = 0.0
        updates = 0
        epoch_start = time.monotonic()
        for begin in range(0, len(order), args.batch):
            part = order[begin:begin+args.batch]
            pieces = [batch(training[g], np.array([i for gg, i in part if gg == g]))
                      for g in range(len(training)) if any(gg == g for gg, _ in part)]
            x, mask, visits, root, outcome, q, explored, action = [torch.cat([p[i] for p in pieces]) for i in range(8)]
            target_policy = torch.nn.functional.one_hot(action, 81).float() if args.arm == 'onehot' else visits
            result = model(x)
            loss = policy_loss(result[0], mask, target_policy)[0].mean()
            target = value_target(root, outcome)
            loss = loss + (result[1] - torch.stack((target, -target), -1)).square().mean()
            if kind == 'entity-q':
                loss = loss + q_loss(result[2], q, explored).mean()
            assert torch.isfinite(loss)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            total_loss += loss.item() * len(x)
            updates += 1
        schedule.step()
        metrics = evaluate()
        metrics.update(epoch=epoch, updates=updates, train_loss=total_loss/epoch_rows,
                       epoch_seconds=time.monotonic()-epoch_start, seconds=time.monotonic()-start)
        history.append(metrics)
        checkpoint = dict(kind=kind, state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()},
            epoch=epoch, fast_entities=True, arm=args.arm, parent_sha256=plan['parent_sha256'])
        torch.save(checkpoint, args.output / f'epoch-{epoch}.pt')
        if metrics['selection_score'] < best:
            best = metrics['selection_score']
            best_epoch = epoch
            torch.save(checkpoint, args.output / 'model.pt')
            # Runtime needs only policy/value; this removes unused Q compute while
            # preserving every trained trunk/policy/value tensor exactly.
            runtime = {**checkpoint, 'kind':'entity', 'state_dict':{k:v for k,v in checkpoint['state_dict'].items() if not k.startswith('action_q.')}}
            torch.save(runtime, args.output / 'runtime.pt')
        manifest = dict(plan=plan, history=history, initial=initial, best_epoch=best_epoch,
            checkpoint_sha256=sha(args.output / 'model.pt'), runtime_sha256=sha(args.output / 'runtime.pt'),
            seconds=time.monotonic()-start, determinism='Fixed seeds/data order; MPS bitwise repeatability is not guaranteed')
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(metrics), flush=True)
    (args.output / 'complete.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
