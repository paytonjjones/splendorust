"""Run one finite, checkpoint-bound external development trial.

Root owns heavy jobs. This driver preserves sources and receipts before play,
then runs the existing paired native benchmark, replay, and summary.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/training_strategy'))
from runtime import Runtime, command_run
from archive_results import sha


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkpoint', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--master', type=int, required=True)
    ap.add_argument('--games', type=int, default=128)
    ap.add_argument('--iterations', type=int, default=128)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--search', choices=('gumbel', 'puct'), default='gumbel')
    ap.add_argument('--depth', type=int, default=16)
    ap.add_argument('--world-pool', type=int, default=3)
    ap.add_argument('--chance-universes', type=int, default=0)
    ap.add_argument('--dynamic-fpu', action='store_true')
    ap.add_argument('--gumbel-max-considered', type=int, default=16)
    ap.add_argument('--binary-directory', type=Path, default=ROOT / 'target/release/examples')
    ap.add_argument('--port', type=int, default=19720)
    ap.add_argument('--device', choices=('mps', 'cpu'), default='mps')
    ap.add_argument('--batch', type=int, default=32)
    args = ap.parse_args()
    assert args.games > 0 and args.games % 2 == 0
    assert 0 < args.workers <= args.games // 2
    assert 0 <= args.iterations < 2**32
    assert 1 <= args.depth <= 124
    assert 0 <= args.world_pool <= 64
    assert 0 <= args.chance_universes <= 64
    assert 1 <= args.gumbel_max_considered <= 81
    assert 1 <= args.batch <= 256
    plan = json.loads((ROOT / 'research/sprint48/PLAN.json').read_text())
    if args.master in (plan['seeds']['final_external']['master'], plan['seeds']['final_canonical']['master']):
        ap.error('Final masters are sealed; use the frozen final-evaluation protocol.')
    run = json.loads((ROOT / 'research/sprint48/RUN.json').read_text())
    assert time.time() < run['deadline_unix'], 'Campaign deadline passed'
    assert not any(trial['status'] == 'running' for trial in run['consumed_trials']), 'Another external trial is active'
    if args.device == 'mps':
        assert not any(branch['status'] == 'running' for branch in run.get('training_branches', [])), 'MPS training is active'
    assert args.master not in [trial['master'] for trial in run['consumed_trials']], 'Master already consumed'
    assert len(run['consumed_trials']) < plan['seeds']['external_exploration']['maximum_trials'], 'Exploratory trial limit reached'
    elapsed = sum(trial.get('wall_seconds', 0) for trial in run['consumed_trials'])
    assert elapsed < plan['exploratory_evaluation_hours_ceiling'] * 3600, 'Exploratory evaluation time limit reached'
    output = args.output.resolve()
    checkpoint = args.checkpoint.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT / 'research/architecture_pivots/service.py',
        ROOT / 'research/architecture_pivots/models.py', ROOT / 'research/architecture_pivots/export.py',
        ROOT / 'research/training_strategy/runtime.py', ROOT / 'research/e95/public_model.py',
        ROOT / 'benchmarks/strength/native/run.py', ROOT / 'benchmarks/strength/native/schedule.py',
        ROOT / 'benchmarks/strength/native/campaign_context.py',
        ROOT / 'benchmarks/strength/native/upstream.py', ROOT / 'benchmarks/strength/native/replay.py',
        ROOT / 'benchmarks/strength/native/summarize.py', ROOT / 'benchmarks/strength/summarize.py',
        ROOT / 'research/sprint48/evidence.py',
        ROOT / 'crates/splendor-agents/src/environment.rs',
        ROOT / 'crates/splendor-agents/src/native_environment.rs',
        ROOT / 'crates/splendor-agents/src/neural_search.rs',
        ROOT / 'crates/splendor-agents/src/transfer.rs',
        ROOT / 'crates/splendor-arena/examples/native_policy_worker.rs',
        ROOT / 'crates/splendor-arena/examples/native_wire/mod.rs']
    source_hashes = {}
    for source in sources:
        relative = source.relative_to(ROOT)
        dest = output / 'sources' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        assert sha(source) == sha(dest)
        source_hashes[str(relative)] = sha(dest)
    binary_hashes = {}
    for name in ('native_policy_worker', 'strength_worker', 'transfer_parity'):
        source = args.binary_directory.resolve(strict=True) / name
        dest = output / 'binaries' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        dest.chmod(0o755)
        binary_hashes[name] = sha(source)
    receipt = dict(schema='sprint48-external-development-v1', started_at=time.time(),
        pid=os.getpid(), checkpoint=str(checkpoint), checkpoint_sha256=sha(checkpoint),
        games=args.games, master=args.master, iterations=args.iterations, workers=args.workers,
        search=args.search, depth=args.depth, world_pool=args.world_pool,
        chance_universes=args.chance_universes,
        dynamic_fpu=args.dynamic_fpu,
        gumbel_max_considered=args.gumbel_max_considered if args.search == 'gumbel' else None,
        port=args.port, device=args.device, batch=args.batch, delay_ms=1,
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_sha256=source_hashes, binary_sha256=binary_hashes,
        status='running', scope='Exploratory native-profile trial; no final strength claim.')
    (output / 'trial.json').write_text(json.dumps(receipt, indent=2) + '\n')
    run['consumed_trials'].append(dict(master=args.master, output=str(output),
        checkpoint_sha256=receipt['checkpoint_sha256'], iterations=args.iterations,
        search=args.search, depth=args.depth, world_pool=args.world_pool,
        chance_universes=args.chance_universes,
        dynamic_fpu=args.dynamic_fpu,
        gumbel_max_considered=receipt['gumbel_max_considered'], workers=args.workers,
        games=args.games, status='running'))
    run['current_stage'] = str(output.relative_to(ROOT))
    (ROOT / 'research/sprint48/RUN.json').write_text(json.dumps(run, indent=2) + '\n')
    try:
        with Runtime([(13, checkpoint)], output / 'service', args.port, args.device,
                     batch=args.batch) as runtime:
            descriptor = runtime.descriptors[13]
            receipt['descriptor_sha256'] = sha(descriptor)
            (output / 'trial.json').write_text(json.dumps(receipt, indent=2) + '\n')
            command_run([output / 'binaries/transfer_parity', descriptor,
                descriptor.with_name('parity.json'), 'real'], output / 'parity-command')
            schedule_command = [sys.executable, ROOT / 'benchmarks/strength/native/schedule.py',
                '--games', args.games, '--master', args.master, '--workers', args.workers,
                '--iterations', args.iterations, '--search', args.search, '--model', descriptor,
                '--depth', args.depth, '--world-pool', args.world_pool,
                '--chance-universes', args.chance_universes,
                '--gumbel-max-considered', args.gumbel_max_considered,
                '--policy-binary', output / 'binaries/native_policy_worker',
                '--strength-binary', output / 'binaries/strength_worker',
                '--output', output / 'arena']
            if args.dynamic_fpu:
                schedule_command.append('--dynamic-fpu')
            command_run(schedule_command, output / 'arena-command')
            raw = output / 'arena/games.jsonl'
            command_run([sys.executable, ROOT / 'benchmarks/strength/native/replay.py',
                raw, '--output', output / 'replay.json'], output / 'replay-command')
            command_run([sys.executable, ROOT / 'benchmarks/strength/native/summarize.py',
                raw, '--output', output / 'summary.json'], output / 'summary-command')
            command_run([sys.executable, ROOT / 'research/sprint48/evidence.py',
                raw, '--output', output / 'evidence.json'], output / 'evidence-command')
            for name, expected in binary_hashes.items():
                assert sha(output / 'binaries' / name) == expected, 'Frozen binary was replaced'
            summary = json.loads((output / 'summary.json').read_text())
            receipt.update(status='complete', completed_at=time.time(),
                raw_sha256=sha(raw), replay_sha256=sha(output / 'replay.json'),
                summary_sha256=sha(output / 'summary.json'), evidence_sha256=sha(output / 'evidence.json'),
                wall_seconds=time.time() - receipt['started_at'])
            print(json.dumps({key: summary[key] for key in ('games', 'statuses',
                'all_requested_credit_bounds', 'paired_bootstrap95_missing_envelope',
                'conservative_hoeffding95_missing_envelope', 'terminal_categories',
                'wall_seconds', 'policy_seconds')}), flush=True)
    except BaseException as error:
        receipt.update(status='failed', failed_at=time.time(), error=repr(error))
        raise
    finally:
        (output / 'trial.json').write_text(json.dumps(receipt, indent=2) + '\n')
        run = json.loads((ROOT / 'research/sprint48/RUN.json').read_text())
        for trial in run['consumed_trials']:
            if trial['output'] == str(output):
                trial['status'] = receipt['status']
                trial['wall_seconds'] = time.time() - receipt['started_at']
        (ROOT / 'research/sprint48/RUN.json').write_text(json.dumps(run, indent=2) + '\n')


if __name__ == '__main__':
    main()
