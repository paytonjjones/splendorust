"""Run the finite Sprint 48 full-corpus entity refit with receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'research/sprint48/PLAN.json'
RUN = ROOT / 'research/sprint48/RUN.json'
READY = ROOT / 'local/research/sprint48/ready/ready.json'
SOURCE_REGISTRY = ROOT / 'research/entity_baseline/expanded-data.json'
SOURCE_CHECKSUMS = ROOT / 'research/entity_baseline/SHA256SUMS'
PREPARED_REGISTRY = ROOT / 'local/research/architecture-pivots/expanded-data.json'
TRAINER = ROOT / 'research/architecture_pivots/train.py'
RUNTIME_PYTHON = ROOT / 'local/strength/inference/bin/python'
OUTPUT_DEFAULT = ROOT / 'local/research/sprint48/refit-01'
BRANCH_NAME = 'native-expanded-onehot-refit'
EXPECTED_REGISTRY_SHA = '4dd2f1a9c8f9e78a192a10da1c686dac3481e76c45a4034a931fae61a4eca581'
EXPECTED_PARENT_SHA = 'ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb'
EXPECTED_BASELINE_SHA = 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def expected_registry_hash():
    for line in SOURCE_CHECKSUMS.read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == 'research/entity_baseline/expanded-data.json':
            return fields[0]
    raise ValueError('The expanded corpus hash is missing from SHA256SUMS')


def validate_registry(source, prepared):
    require(sha(SOURCE_REGISTRY) == EXPECTED_REGISTRY_SHA, 'Committed corpus registry hash differs')
    require(expected_registry_hash() == EXPECTED_REGISTRY_SHA, 'SHA256SUMS corpus hash differs')
    reference = json.loads(SOURCE_REGISTRY.read_text())
    actual = json.loads(prepared.read_text())
    for split in ('train', 'dev'):
        require(len(reference[split]) == len(actual[split]), f'{split} registry file count differs')
        for expected, entry in zip(reference[split], actual[split]):
            for field in ('source_sha256', 'context_sha256', 'inputs_sha256', 'native', 'rows'):
                require(entry[field] == expected[field], f'{split} registry differs at {field}')
            for field in ('source', 'context', 'inputs'):
                path = Path(entry[field])
                require(path.is_file(), f'Missing {split} corpus input: {path}')
    require(actual['setup_counts'] == reference['setup_counts'], 'Corpus setup counts differ')
    require(actual['setup_counts'] == {'train': 30000, 'dev': 2000}, 'Unexpected corpus split size')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument('--trainer', type=Path, default=TRAINER,
                        help='Trainer entry point; normally the pinned research trainer')
    parser.add_argument('--python', type=Path, default=RUNTIME_PYTHON,
                        help='Python runtime; normally the pinned inference runtime')
    parser.add_argument('--dry-run', action='store_true', help='Validate receipts and print the command; do not write or start training')
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve()
    trainer = args.trainer.resolve()
    # Preserve venv/uv interpreter symlinks: resolving them can switch away
    # from the environment that owns Torch and its MPS build.
    runtime_python = Path(os.path.abspath(args.python))
    fit_output = output / 'fit'

    campaign = json.loads(RUN.read_text())
    plan = json.loads(PLAN.read_text())
    ready = json.loads(READY.read_text())
    require(campaign['status'] == 'active', 'Sprint campaign is not active')
    require(campaign.get('final_seed_sealed') is True, 'Final seeds must remain sealed during training')
    require(not any(t.get('status') == 'running' for t in campaign.get('consumed_trials', [])),
            'Stop and receipt the active external trial before MPS training')
    require(plan['maximum_new_training_branches'] >= 1, 'The training-branch allowance is exhausted')
    require(plan['first_candidate']['runtime_sha256'] == EXPECTED_PARENT_SHA, 'Plan parent differs')
    require(ready['candidate_sha256'] == EXPECTED_PARENT_SHA, 'Prepared parent receipt differs')
    require(ready['baseline_sha256'] == EXPECTED_BASELINE_SHA, 'Prepared baseline receipt differs')
    parent = Path(ready['candidate']).resolve(strict=True)
    require(sha(parent) == EXPECTED_PARENT_SHA, 'Prepared parent bytes differ')
    require(runtime_python.is_file(), f'Missing Python runtime: {runtime_python}')
    require(trainer.is_file(), f'Missing trainer: {trainer}')
    require(not output.exists(), f'Output already exists; choose a fresh directory: {output}')
    deadline = datetime.fromisoformat(campaign['deadline_utc'].replace('Z', '+00:00'))
    require(datetime.now(timezone.utc) < deadline, 'Sprint deadline has passed')
    data = validate_registry(SOURCE_REGISTRY, PREPARED_REGISTRY)

    command = [str(runtime_python), str(trainer), '--kind', 'entity', '--parent', str(parent),
               '--data-scale', 'expanded', '--epochs', '2', '--batch', '512', '--device', 'mps',
               '--fast-entities', '--output', str(fit_output)]
    source_files = [trainer, TRAINER.with_name('models.py'), ROOT / 'research/flywheel_model.py',
                    ROOT / 'research/e95/public_model.py', ROOT / 'research/entity_baseline/bootstrap.py',
                    ROOT / 'research/sprint48/run_refit.py']
    code_hashes = {}
    for path in source_files:
        try:
            key = str(path.relative_to(ROOT))
        except ValueError:
            key = str(path)
        code_hashes[key] = sha(path)
    data_sources = []
    for split in ('train', 'dev'):
        for entry in data[split]:
            data_sources.append({
                'split': split, 'native': entry['native'], 'rows': entry['rows'],
                'source': entry['source'], 'source_sha256': entry['source_sha256'],
                'context': entry['context'], 'context_sha256': entry['context_sha256'],
                'inputs': entry['inputs'], 'inputs_sha256': entry['inputs_sha256'],
            })

    if args.dry_run:
        print(json.dumps({
            'dry_run': True, 'receipt_output': str(output), 'trainer_output': str(fit_output),
            'command': command,
            'parent_sha256': sha(parent), 'source_registry_sha256': sha(SOURCE_REGISTRY),
            'prepared_registry_sha256': sha(PREPARED_REGISTRY), 'train_files': len(data['train']),
            'dev_files': len(data['dev']), 'train_setups': data['setup_counts']['train'],
            'dev_setups': data['setup_counts']['dev'], 'deadline_utc': campaign['deadline_utc'],
            'code_sha256': code_hashes,
        }, indent=2))
        return 0

    output.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    receipt = {
        'schema': 'sprint48-refit-run-v1', 'branch': BRANCH_NAME, 'branch_index': 1,
        'started_utc': started, 'deadline_utc': campaign['deadline_utc'],
        'driver_pid': os.getpid(), 'trainer_pid': None, 'status': 'starting',
        'target': campaign['target'], 'parent': str(parent), 'parent_sha256': sha(parent),
        'baseline_sha256': ready['baseline_sha256'], 'source_registry': str(SOURCE_REGISTRY),
        'source_registry_sha256': sha(SOURCE_REGISTRY),
        'prepared_registry': str(PREPARED_REGISTRY),
        'prepared_registry_sha256': sha(PREPARED_REGISTRY),
        'setup_counts': data['setup_counts'], 'data_sources': data_sources,
        'code_sha256': code_hashes, 'command': command, 'cwd': str(ROOT),
        'fit': {'kind': 'entity', 'epochs': 2, 'batch': 512, 'device': 'mps',
                'fast_entities': True, 'optimizer': 'fresh AdamW', 'selection': 'existing full-dev policy CE + 4 outcome Brier'},
        'trainer_log': str(output / 'trainer.log'),
        'receipt_output': str(output), 'trainer_output': str(fit_output),
    }
    (output / 'run.json').write_text(json.dumps(receipt, indent=2) + '\n')

    process = None
    try:
        with (output / 'trainer.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
        receipt['trainer_pid'] = process.pid
        receipt['trainer_pgid'] = process.pid
        receipt['trainer_started_utc'] = utc_now()
        receipt['status'] = 'running'
        (output / 'process.json').write_text(json.dumps({
            'pid': process.pid, 'pgid': process.pid, 'command': command,
            'started_utc': receipt['trainer_started_utc'], 'cwd': str(ROOT),
        }, indent=2) + '\n')
        (output / 'run.json').write_text(json.dumps(receipt, indent=2) + '\n')

        expired = False
        while process.poll() is None:
            if datetime.now(timezone.utc) >= deadline:
                expired = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                break
            time.sleep(0.5)

        code = process.wait()
        manifest_path = fit_output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
        observed_epochs = len(manifest.get('history', [])) if manifest else 0
        complete = code == 0 and manifest is not None and observed_epochs == 2
        receipt.update({
            'finished_utc': utc_now(), 'returncode': code,
            'last_complete_epoch': observed_epochs,
            'selected_model_sha256': sha(fit_output / 'model.pt') if (fit_output / 'model.pt').is_file() else None,
            'latest_sha256': sha(fit_output / 'latest.pt') if (fit_output / 'latest.pt').is_file() else None,
            'trainer_manifest_sha256': sha(manifest_path) if manifest_path.is_file() else None,
            'status': 'deadline_stopped' if expired else ('complete' if complete else 'failed'),
        })
        if expired or not complete:
            failure = {
                'schema': 'sprint48-refit-failure-v1', 'status': receipt['status'],
                'deadline_utc': campaign['deadline_utc'], 'returncode': code,
                'last_complete_epoch': observed_epochs,
                'note': 'Keep partial checkpoints, manifest, metrics, and trainer.log. Do not resume in place.',
            }
            (output / 'failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        (output / 'exit.json').write_text(json.dumps({
            'returncode': code, 'finished_utc': receipt['finished_utc'],
            'deadline_stopped': expired, 'last_complete_epoch': observed_epochs,
        }, indent=2) + '\n')
        (output / 'run.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return 0 if receipt['status'] == 'complete' else 1
    except BaseException as exc:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
        failure = {
            'schema': 'sprint48-refit-failure-v1', 'status': 'failed',
            'time_utc': utc_now(), 'error_type': type(exc).__name__, 'error': str(exc),
            'note': 'Keep partial checkpoints, manifest, metrics, and trainer.log. Do not resume in place.',
        }
        (output / 'failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        receipt.update(status='failed', finished_utc=utc_now(), error=str(exc))
        (output / 'run.json').write_text(json.dumps(receipt, indent=2) + '\n')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
