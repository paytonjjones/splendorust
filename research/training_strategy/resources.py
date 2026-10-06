"""Approve scheduling changes from retained whole-game parity measurements."""
import json
from data import ROOT, sha


def evaluation_resources(workers):
    assert workers in (32, 64)
    if workers == 32:
        return dict(eval_threads=32)
    path = ROOT / 'local/research/training-strategy/resource-scaling/complete.json'
    receipt = json.loads(path.read_text())
    assert receipt['whole_game_parity'] and receipt['excluded_from_learning_and_strength']
    a, b = (receipt['results']['arena-' + str(n)] for n in (32, 64))
    assert a['record_set_sha256'] == b['record_set_sha256']
    assert a['source_id'] == b['source_id']
    assert a['runtime_seconds'] / b['runtime_seconds'] >= 1.10, '64 workers did not provide a useful whole-game gain'
    return dict(eval_threads=64, fixed_tensor_batch=32,
                resource_parity_sha256=sha(path), resource_parity_path=str(path),
                measured_shared_host_arena_speedup=a['runtime_seconds'] / b['runtime_seconds'],
                authorization='User requested more Mac resources; only scheduling changes.')
