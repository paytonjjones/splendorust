"""Wait for the frozen trial06 receipt, then run the fixed trial07 once.

This finite supervisor is deliberately independent of the Codex turn lifetime.
It does not edit RUN.json. The normal external-trial driver owns that registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / 'local/research/sprint48/queue-06-07'
TRIAL06 = ROOT / 'local/research/sprint48/external-06'
TRIAL07 = ROOT / 'local/research/sprint48/external-07'
DEADLINE_UTC = '2026-10-05T19:35:52+00:00'
DEADLINE = datetime.fromisoformat(DEADLINE_UTC).timestamp()
PYTHON = ROOT / 'local/strength/inference/bin/python'
CHECKPOINT = ROOT / 'local/research/sprint48/ready/first/onehot/runtime.pt'
BINARY_DIR = ROOT / 'local/research/sprint48/build-dynamic/release/examples'
EXPECTED06 = {
    'master': 17706000000, 'games': 128, 'iterations': 6400,
    'workers': 64, 'search': 'puct', 'depth': 64, 'world_pool': 3,
    'chance_universes': 3, 'dynamic_fpu': True, 'device': 'mps',
    'batch': 32, 'port': 19726,
    'checkpoint_sha256': '44ebfc8f46cd3c7f4288183313cb4c69e22337b8b7169f6e1bc5e920553d6e6f',
}
EXPECTED07 = {
    'master': 17707000000, 'games': 128, 'iterations': 6400,
    'workers': 64, 'search': 'puct', 'depth': 64, 'world_pool': 3,
    'chance_universes': 3, 'dynamic_fpu': True, 'device': 'mps',
    'batch': 32, 'port': 19727,
    'checkpoint_sha256': 'ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def command07() -> list[str]:
    return [str(PYTHON), 'research/sprint48/run_external.py',
        '--checkpoint', 'local/research/sprint48/ready/first/onehot/runtime.pt',
        '--output', 'local/research/sprint48/external-07',
        '--master', '17707000000', '--games', '128', '--iterations', '6400',
        '--workers', '64', '--search', 'puct', '--depth', '64',
        '--world-pool', '3', '--chance-universes', '3', '--dynamic-fpu',
        '--binary-directory', 'local/research/sprint48/build-dynamic/release/examples',
        '--port', '19727', '--device', 'mps', '--batch', '32']


def check_fixed_receipt(receipt: dict, expected: dict) -> None:
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(f'{field} mismatch: {receipt.get(field)!r} != {value!r}')


def validate_trial06(root: Path = ROOT) -> dict:
    output = root / 'local/research/sprint48/external-06'
    trial_path = output / 'trial.json'
    trial = json.loads(trial_path.read_text())
    check_fixed_receipt(trial, EXPECTED06)
    if trial.get('status') != 'complete':
        raise ValueError(f'trial06 status is {trial.get("status")!r}')
    raw = output / 'arena/games.jsonl'
    replay_path = output / 'replay.json'
    evidence_path = output / 'evidence.json'
    for path in (raw, replay_path, evidence_path, output / 'summary.json'):
        if not path.is_file():
            raise ValueError(f'missing completion artifact: {path}')
    raw_hash = sha(raw)
    if trial.get('raw_sha256') != raw_hash:
        raise ValueError('trial06 raw hash does not match')
    replay = json.loads(replay_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    if replay.get('checked_games') != 128 or replay.get('raw_sha256') != raw_hash:
        raise ValueError('trial06 replay is incomplete or refers to different raw rows')
    if evidence.get('games') != 128 or evidence.get('setup_blocks') != 64:
        raise ValueError('trial06 evidence does not cover 128 games / 64 setup blocks')
    if evidence.get('evidence_rejections') != []:
        raise ValueError(f'trial06 evidence rejected: {evidence.get("evidence_rejections")}')
    if evidence.get('raw_sha256') != raw_hash:
        raise ValueError('trial06 evidence refers to different raw rows')
    run = json.loads((root / 'research/sprint48/RUN.json').read_text())
    matches = [row for row in run['consumed_trials'] if row.get('master') == EXPECTED06['master']]
    if len(matches) != 1 or matches[0].get('status') != 'complete':
        raise ValueError('RUN.json does not record trial06 as complete')
    service_path = output / 'service/run.json'
    service = json.loads(service_path.read_text())
    if service.get('batch') != 32:
        raise ValueError('trial06 service receipt batch mismatch')
    service_pid = service.get('pid')
    if not isinstance(service_pid, int) or process_is_service(service_pid, EXPECTED06['port']):
        raise ValueError('trial06 owned inference service is still active')
    if any(branch.get('status') == 'running' for branch in run.get('training_branches', [])):
        raise ValueError('RUN.json still records active training')
    if (root / 'local/research/sprint48/external-07').exists():
        raise ValueError('trial07 output already exists; refusing duplicate launch')
    if sha(root / 'local/research/sprint48/ready/first/onehot/runtime.pt') != EXPECTED07['checkpoint_sha256']:
        raise ValueError('frozen trial07 checkpoint hash changed')
    for name in ('native_policy_worker', 'strength_worker', 'transfer_parity'):
        if not (root / 'local/research/sprint48/build-dynamic/release/examples' / name).is_file():
            raise ValueError(f'missing pinned trial07 binary: {name}')
    return {'trial06_trial_sha256': sha(trial_path), 'raw_sha256': raw_hash,
        'replay_sha256': sha(replay_path), 'evidence_sha256': sha(evidence_path),
        'trial06_status': trial['status'], 'replay_games': replay['checked_games'],
        'evidence_rejections': evidence['evidence_rejections'],
        'service_pid': service_pid, 'service_stopped': True}


def process_is_service(pid: int, port: int) -> bool:
    try:
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
            capture_output=True, text=True, check=False)
    except OSError:
        return False
    command = result.stdout.strip()
    return bool(command and 'service.py' in command and f'--port {port}' in command)


def launch_trial07(queue: Path, root: Path = ROOT,
        popen: Callable = subprocess.Popen) -> subprocess.Popen:
    cmd = command07()
    log_path = queue / 'trial07.log'
    queue.mkdir(parents=True, exist_ok=True)
    log = log_path.open('w')
    try:
        process = popen(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    finally:
        log.close()
    atomic_json(queue / 'trial07-process.json', {
        'pid': process.pid, 'pgid': process.pid, 'command': cmd,
        'cwd': str(root), 'log': str(log_path),
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'checkpoint_sha256': EXPECTED07['checkpoint_sha256']})
    return process


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--poll-seconds', type=int, default=60)
    ap.add_argument('--deadline-unix', type=float, default=DEADLINE)
    args = ap.parse_args()
    if args.poll_seconds < 60:
        ap.error('--poll-seconds must be at least 60')
    QUEUE.mkdir(parents=True, exist_ok=False)
    cmd = command07()
    record = {
        'schema': 'sprint48-trial06-07-supervisor-v1',
        'status': 'waiting_for_trial06', 'supervisor_pid': os.getpid(),
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'deadline_unix': args.deadline_unix,
        'source_path': str(Path(__file__).resolve()),
        'source_sha256': sha(Path(__file__).resolve()),
        'trial06_output': str(TRIAL06), 'trial06_expected': EXPECTED06,
        'trial07_command': cmd, 'trial07_checkpoint_sha256': sha(CHECKPOINT),
        'trial07_binary_sha256': {name: sha(BINARY_DIR / name)
            for name in ('native_policy_worker', 'strength_worker', 'transfer_parity')},
        'poll_seconds': args.poll_seconds,
    }
    atomic_json(QUEUE / 'supervisor.json', record)
    atomic_json(QUEUE / 'trial07-command.json', {
        'command': cmd, 'cwd': str(ROOT), 'master': EXPECTED07['master'],
        'settings': EXPECTED07})
    # Store a live PID receipt before entering the potentially long bounded wait.
    atomic_json(QUEUE / 'supervisor-process.json', {
        'pid': os.getpid(), 'pgid': os.getpgrp(),
        'started_utc': record['started_utc']})
    while True:
        if time.time() >= args.deadline_unix:
            record.update(status='failed', failed_utc=datetime.now(timezone.utc).isoformat(),
                failure='48-hour deadline reached before trial06 completed')
            atomic_json(QUEUE / 'supervisor.json', record)
            return 2
        try:
            trial06 = json.loads((TRIAL06 / 'trial.json').read_text())
        except (OSError, json.JSONDecodeError):
            trial06 = None
        if trial06 and trial06.get('status') == 'failed':
            record.update(status='failed', failed_utc=datetime.now(timezone.utc).isoformat(),
                failure='trial06 reports failed; no retry')
            atomic_json(QUEUE / 'supervisor.json', record)
            return 3
        if trial06 and trial06.get('status') == 'complete':
            break
        time.sleep(min(args.poll_seconds, max(1, args.deadline_unix - time.time())))
    try:
        source_evidence = validate_trial06()
        record.update(status='trial06_verified', trial06_verified_utc=datetime.now(timezone.utc).isoformat(),
            trial06_evidence=source_evidence)
        atomic_json(QUEUE / 'supervisor.json', record)
        if time.time() >= args.deadline_unix:
            raise TimeoutError('Deadline reached before trial07 launch')
        # Recheck no other process modified fixed launch inputs while waiting.
        if sha(CHECKPOINT) != EXPECTED07['checkpoint_sha256']:
            raise ValueError('trial07 checkpoint changed after preflight')
        for name, expected in record['trial07_binary_sha256'].items():
            if sha(BINARY_DIR / name) != expected:
                raise ValueError(f'trial07 binary changed after preflight: {name}')
        process = launch_trial07(QUEUE)
        record.update(status='trial07_running', launched_utc=datetime.now(timezone.utc).isoformat(),
            trial07_pid=process.pid, trial07_pgid=process.pid,
            trial07_log=str(QUEUE / 'trial07.log'))
        atomic_json(QUEUE / 'supervisor.json', record)
        while process.poll() is None:
            if time.time() >= args.deadline_unix:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise TimeoutError('Deadline reached; trial07 process group terminated')
            time.sleep(min(args.poll_seconds, max(1, args.deadline_unix - time.time())))
        code = process.returncode
        atomic_json(QUEUE / 'trial07-process-exit.json', {'returncode': code,
            'finished_utc': datetime.now(timezone.utc).isoformat()})
        if code != 0:
            raise RuntimeError(f'trial07 driver exited with code {code}')
        trial07 = json.loads((TRIAL07 / 'trial.json').read_text())
        check_fixed_receipt(trial07, EXPECTED07)
        if trial07.get('status') != 'complete':
            raise ValueError(f'trial07 status is {trial07.get("status")!r}')
        record.update(status='complete', completed_utc=datetime.now(timezone.utc).isoformat(),
            trial07_exit_code=code, trial07_trial_sha256=sha(TRIAL07 / 'trial.json'))
        atomic_json(QUEUE / 'supervisor.json', record)
        return 0
    except BaseException as error:
        record.update(status='failed', failed_utc=datetime.now(timezone.utc).isoformat(),
            failure=repr(error))
        atomic_json(QUEUE / 'supervisor.json', record)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
