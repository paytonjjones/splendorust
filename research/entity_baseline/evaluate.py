"""Run a fresh canonical Gumbel128 screen from this immutable Entity parent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHECKPOINT_HASH = 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True, help='A new, disjoint master seed')
    parser.add_argument('--port', type=int, default=19546)
    parser.add_argument('--threads', type=int, default=32)
    parser.add_argument('--device', choices=('cpu', 'mps'), default='mps')
    parser.add_argument('--screen', type=int, default=2000)
    parser.add_argument('--confirm', type=int, default=0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    checkpoint = args.output / 'model.pt'
    shutil.copyfile(HERE / 'model.pt', checkpoint)
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == CHECKPOINT_HASH
    subprocess.run([sys.executable, ROOT / 'research/architecture_pivots/export.py',
                    checkpoint, '--port', str(args.port), '--slot', '13'], cwd=ROOT, check=True)
    command = [sys.executable, ROOT / 'research/architecture_pivots/service.py',
               '--model', f'13:{checkpoint}', '--port', str(args.port), '--device', args.device,
               '--batch', '32', '--delay-ms', '1', '--fast-entities']
    champion = ROOT / 'research/CHAMPION.json'
    champion_before = champion.read_bytes()
    (args.output / 'inference.json').write_text(json.dumps(dict(
        checkpoint_sha256=CHECKPOINT_HASH, service_command=list(map(str, command)),
        batch=32, delay_ms=1, kind='entity', history_mode=0,
        original_screen_seed=5180000000, fresh_seed=args.seed,
        fixed_budget='Gumbel128/depth16/world_pool3',
        official_champion_sha256=hashlib.sha256(champion_before).hexdigest()), indent=2) + '\n')
    with (args.output / 'service.log').open('w') as log:
        service = subprocess.Popen(list(map(str, command)), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while True:
                if service.poll() is not None:
                    raise RuntimeError(f'Inference service failed; see {args.output / "service.log"}')
                try:
                    with socket.create_connection(('127.0.0.1', args.port), timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Inference service did not start')
                    time.sleep(.1)
            env = os.environ.copy()
            env.update(SPLENDOR_CANDIDATE_MODEL=str(checkpoint.with_suffix('.bin')),
                       SPLENDOR_BEST_MODEL=str(ROOT / 'research/e81/model/model.bin'))
            result = subprocess.run([sys.executable, ROOT / 'scripts/promote.py',
                '--candidate', 'flywheel-gumbel-candidate', '--baseline', 'flywheel-gumbel',
                '--players', '2', '--screen', str(args.screen), '--confirm', str(args.confirm),
                '--seed', str(args.seed), '--threads', str(args.threads), '--iterations', '128',
                '--depth', '16', '--output', str(args.output / 'gate')], cwd=ROOT, env=env)
            if result.returncode not in (0, 2):
                raise RuntimeError(f'Promotion runner failed: {result.returncode}')
        finally:
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
            assert champion.read_bytes() == champion_before, 'Official champion changed'


if __name__ == '__main__':
    main()
