#!/usr/bin/env python3
"""Pack and CPU-check a self-contained Entity policy/value ensemble."""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/architecture_pivots'))
sys.path.insert(0, str(ROOT / 'research/e95'))
sys.path.insert(0, str(ROOT / 'research'))
from models import create, load
from public_model import inputs
from flywheel_model import DTYPE, sha


def state(path):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    if payload.get('kind') != 'entity':
        raise ValueError(f'{path} is not an Entity checkpoint')
    return payload


def member(payload):
    model = create('entity')
    model.load_state_dict(payload['state_dict'], strict=True)
    model.fast_tokenization = payload.get('fast_entities', False)
    return model.eval()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', type=Path, default=ROOT / 'local/research/sprint48/refit-01/fit/model.pt')
    parser.add_argument('--value', type=Path, default=ROOT / 'local/research/sprint48/ready/first/onehot/runtime.pt')
    parser.add_argument('--output', type=Path, default=ROOT / 'local/research/sprint48/entity-ensemble.pt')
    parser.add_argument('--rows', type=int, default=32)
    args = parser.parse_args()
    if args.rows < 1 or args.rows > 256:
        parser.error('--rows must be from 1 through 256')
    if args.output.exists():
        parser.error(f'output already exists: {args.output}')
    if not args.policy.is_file() or not args.value.is_file():
        parser.error('both member checkpoints must exist')

    policy_payload = state(args.policy)
    value_payload = state(args.value)
    policy_fast = bool(policy_payload.get('fast_entities', False))
    value_fast = bool(value_payload.get('fast_entities', False))
    if policy_fast != value_fast:
        parser.error('member checkpoints must use the same fast_entities setting')
    policy_sha = sha(args.policy)
    value_sha = sha(args.value)
    packed = create('entity-ensemble')
    packed.load_state_dict({
        **{f'policy_member.{key}': tensor for key, tensor in policy_payload['state_dict'].items()},
        **{f'value_member.{key}': tensor for key, tensor in value_payload['state_dict'].items()},
    }, strict=True)
    payload = {
        'kind': 'entity-ensemble',
        'state_dict': packed.state_dict(),
        'fast_entities': policy_fast,
        'ensemble': {
            'policy_member_sha256': policy_sha,
            'value_member_sha256': value_sha,
            'policy': 'policy_member logits and signed value',
            'value': 'arithmetic mean of both signed values',
        },
    }

    rows = np.memmap(ROOT / 'local/research/e95/dev/000000/data.bin', mode='r', dtype=DTYPE)
    context = np.memmap(ROOT / 'local/research/e95/dev/000000/data.context.bin',
                        mode='r', dtype='<f4').reshape(-1, 7)
    indices = np.linspace(0, len(rows) - 1, min(args.rows, len(rows)), dtype=int)
    x = torch.from_numpy(inputs(rows['x'][indices].copy(), context[indices].copy(), True))

    policy_model = member(policy_payload)
    value_model = member(value_payload)
    with torch.inference_mode():
        policy_logits, policy_values = policy_model(x)
        _, second_values = value_model(x)
        expected_values = (policy_values + second_values) * .5

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + '.tmp')
    if temporary.exists():
        parser.error(f'temporary output already exists: {temporary}')
    torch.save(payload, temporary)
    # Test outputs from only the embedded checkpoint; member paths are unused.
    loaded_model, loaded_payload = load(temporary, 'cpu')
    if loaded_payload['ensemble'] != payload['ensemble']:
        temporary.unlink()
        raise AssertionError('embedded member hashes changed during save')
    with torch.inference_mode():
        combined_logits, combined_values = loaded_model(x)
    if not torch.equal(combined_logits, policy_logits):
        temporary.unlink()
        raise AssertionError('ensemble policy logits differ from the policy member')
    if not torch.equal(combined_values, expected_values):
        temporary.unlink()
        raise AssertionError('ensemble values differ from the signed arithmetic mean')
    os.replace(temporary, args.output)
    receipt = {
        'checkpoint': str(args.output),
        'checkpoint_sha256': sha(args.output),
        'kind': payload['kind'],
        'rows_checked': len(indices),
        'policy_logits_exact': True,
        'signed_value_mean_exact': True,
        'member_sources': {
            'policy_sha256': policy_sha,
            'value_sha256': value_sha,
        },
        'member_paths_embedded': False,
    }
    args.output.with_suffix(args.output.suffix + '.json').write_text(
        json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
