"""Resume interrupted first-study screens without recollecting or refitting."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from data import ROOT, prepare, sha
from runtime import Runtime, command_run
from strategy_summary import canonical


COMPARISONS = [('onehot', 14, 13, 5431000000),
               ('visits', 15, 13, 5432000000),
               ('visits-q', 16, 13, 5433000000),
               ('visits-v-onehot', 15, 14, 5434000000),
               ('q-v-visits', 16, 15, 5435000000)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--port', type=int, default=19620)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    first, recovery = args.first.resolve(), args.recovery.resolve()
    plan = json.loads((first / 'plan.json').read_text())
    progress_before = json.loads((first / 'progress.json').read_text())
    assert not (first / 'complete.json').exists()
    lock = (ROOT / 'local/research/training-strategy.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # A dead process and an available lock are required before recovery.
    old = subprocess.run(['ps', '-p', str(progress_before['pid']), '-o', 'command='],
                         capture_output=True, text=True)
    assert old.returncode != 0, 'Original controller PID is still present'
    assert all(sha(ROOT / name) == expected
               for name, expected in plan['source_files'].items())
    # Collection is complete. Preserve its original binary identity; recovery
    # uses only arena screens and must not require a rebuilt collector's bytes.
    collector_now = sha(ROOT / 'target/release/examples/rich_selfplay')
    baseline = ROOT / 'research/entity_baseline/model.pt'
    assert sha(baseline) == plan['baseline_sha256']
    champion = ROOT / 'research/CHAMPION.json'
    champion_before = champion.read_bytes()
    assert champion_before == subprocess.check_output(
        ['git', 'show', '7367b05:research/CHAMPION.json'], cwd=ROOT)
    stages = list(progress_before['completed_stages'])
    prefix = ['scaling-4', 'scaling-8', 'scaling-16', 'scaling-32',
              'train', 'dev', 'fit-onehot', 'fit-visits', 'fit-visits-q']
    expected = prefix + ['screen-' + item[0] for item in COMPARISONS]
    assert stages == expected[:len(stages)] and len(stages) >= len(prefix)
    for corpus, games in [('train', 2000), ('dev', 400)]:
        prepare(first / corpus)
        completion = json.loads((first / corpus / 'complete.json').read_text())
        assert completion['games'] == games and completion['counts'] == [games, 0, 0]
        assert completion['all_games_replayed']
    model_hashes = {13: sha(baseline)}
    models = [(13, baseline)]
    for slot, arm in enumerate(plan['arms'], 14):
        manifest = json.loads((first / arm / 'manifest.json').read_text())
        assert sha(first / arm / 'model.pt') == manifest['checkpoint_sha256']
        assert sha(first / arm / 'runtime.pt') == manifest['runtime_sha256']
        assert json.loads((first / ('fit-' + arm) / 'exit.json').read_text())['returncode'] == 0
        models.append((slot, first / arm / 'runtime.pt'))
        model_hashes[slot] = manifest['runtime_sha256']
    completed = len(stages) - len(prefix)
    for name, _, _, seed in COMPARISONS[:completed]:
        evidence = canonical(first / ('screen-' + name) / 'screen.json')
        assert evidence['games'] == 2000 and evidence['seed'] == seed
        assert json.loads((first / ('screen-' + name + '-command') / 'exit.json').read_text())['returncode'] in (0, 2)
    print(json.dumps({'checked_completed_stages': stages,
                      'remaining_screens': [c[0] for c in COMPARISONS[completed:]],
                      'model_hashes': model_hashes}), flush=True)
    if args.check_only:
        return
    recovery.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema='interrupted-screen-recovery-v1', pid=os.getpid(),
                   started_at=time.time(), original_progress=progress_before,
                   model_hashes=model_hashes, controller_sha256=sha(__file__),
                   reason='Original controller and its process handle were absent; no terminal receipt.',
                   original_collector_sha256=plan['collector_sha256'],
                   current_unused_collector_sha256=collector_now,
                   repeated_games_excluded=True, preserved=[])
    (recovery / 'plan.json').write_text(json.dumps(receipt, indent=2) + '\n')
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()

    def progress(stage):
        state = dict(pid=os.getpid(), stage=stage, updated_at=time.time(),
                     completed_stages=stages, recovery=str(recovery))
        (first / 'progress.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)

    try:
        with Runtime(models, recovery / 'arena-service', args.port, 'mps') as runtime:
            for name, candidate, baseline_slot, seed in COMPARISONS[completed:]:
                stage = 'screen-' + name
                # Preserve every interrupted file before using the registered path.
                for directory in [first / stage, first / (stage + '-command')]:
                    if directory.exists():
                        preserved = recovery / 'interrupted' / directory.name
                        preserved.parent.mkdir(parents=True, exist_ok=True)
                        directory.rename(preserved)
                        receipt['preserved'].append(str(preserved))
                (recovery / 'plan.json').write_text(json.dumps(receipt, indent=2) + '\n')
                progress(stage)
                env = dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[candidate]),
                           SPLENDOR_BEST_MODEL=str(runtime.descriptors[baseline_slot]))
                command_run([sys.executable, ROOT / 'scripts/promote.py',
                             '--candidate', 'flywheel-gumbel-candidate',
                             '--baseline', 'flywheel-gumbel', '--players', 2,
                             '--screen', 2000, '--confirm', 0, '--seed', seed,
                             '--threads', 32, '--iterations', 128, '--depth', 16,
                             '--output', first / stage], first / (stage + '-command'),
                            env, accepted=(0, 2))
                evidence = canonical(first / stage / 'screen.json')
                assert evidence['games'] == 2000 and evidence['seed'] == seed
                stages.append(stage)
        assert champion.read_bytes() == champion_before
        assert all(sha(ROOT / name) == expected
                   for name, expected in plan['source_files'].items())
        assert all(sha(path) == model_hashes[slot] for slot, path in models)
        progress('complete')
        (first / 'complete.json').write_text(json.dumps(dict(
            plan=plan, stages=stages, completed_at=time.time(),
            official_champion_unchanged=True, recovery=receipt), indent=2) + '\n')
        (recovery / 'complete.json').write_text(json.dumps(receipt, indent=2) + '\n')
    except BaseException as error:
        (recovery / 'failure.json').write_text(json.dumps(dict(
            error=repr(error), stages=stages, pid=os.getpid()), indent=2) + '\n')
        raise
    finally:
        assert champion.read_bytes() == champion_before


if __name__ == '__main__':
    main()
