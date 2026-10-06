"""One bounded exploratory comparison after the user's early-close request."""
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from data import ROOT, sha
from runtime import Runtime, command_run
from status import process


def main():
    root = ROOT / 'local/research/training-strategy'
    out = root / 'early-close'
    stop = json.loads((out / 'stop-receipt.json').read_text())
    lock = (ROOT / 'local/research/training-strategy.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    deadline = stop['started_at'] + 1500
    plan = dict(pid=os.getpid(), started_at=time.time(), deadline=deadline,
        games=256, seed=5492000000, workers=64, iterations=128, depth=16,
        exploratory=True, registered_study_complete=False,
        rule_sha256=sha(Path(__file__).with_name('CLOSEOUT.md')))
    (out / 'pilot-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    saved = json.loads((root / 'second/fit-frozen/process.json').read_text())
    while process(saved['pid'], saved['command'])['live']:
        assert time.time() < deadline - 900, 'Insufficient time for bounded pilot'
        time.sleep(5)
    fits = {}
    for label in ('iterative', 'frozen'):
        directory = root / 'second' / label
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert len(manifest['history']) == 4
        assert sha(directory / 'model.pt') == manifest['checkpoint_sha256']
        assert sha(directory / 'runtime.pt') == manifest['runtime_sha256']
        fits[label] = manifest
    (out / 'fit-artifacts.json').write_text(json.dumps(dict(fits=fits,
        frozen_parent_exit_receipt_present=(root / 'second/fit-frozen/exit.json').exists(),
        frozen_process_exit_code=None), indent=2) + '\n')
    with Runtime([(15, root / 'second/iterative/runtime.pt'),
                  (16, root / 'second/frozen/runtime.pt')], out / 'pilot-service') as runtime:
        environment = dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[15]),
                           SPLENDOR_BEST_MODEL=str(runtime.descriptors[16]))
        # A separate watchdog stops only this pilot's descendants at its deadline.
        command_run([sys.executable, Path(__file__).with_name('deadline_command.py'),
            str(deadline), sys.executable, ROOT / 'scripts/promote.py',
            '--candidate', 'flywheel-gumbel-candidate', '--baseline', 'flywheel-gumbel',
            '--players', 2, '--screen', 256, '--confirm', 0, '--seed', 5492000000,
            '--threads', 64, '--iterations', 128, '--depth', 16,
            '--output', out / 'iterative-v-frozen'], out / 'pilot-command',
            environment, accepted=(0, 2, 124))


if __name__ == '__main__':
    main()
