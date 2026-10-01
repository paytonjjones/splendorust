#!/usr/bin/env python3
"""Verify frozen source/runtime, lossless archives and completed replay evidence."""
import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from upstream import ROOT, SOURCE, PIN, sha

BASE = Path(__file__).resolve().parent
EXPECTED = {'screen': (2000, 4110000000, 128),
            'confirmation': (20000, 4120000000, 128),
            'higher-search': (2000, 4150000000, 800)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', action='store_true',
                        help='also verify local built binaries and upstream checkout')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads((BASE / 'frozen-manifest.json').read_text())
    for name, digest in frozen['harness_sha256'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in frozen['source_model_binary_sha256'].items():
        if name.startswith('target/') or name.startswith('local/'):
            if not args.runtime:
                continue
        assert sha(ROOT / name) == digest, name
    protected = ['crates/splendor-core', 'crates/splendor-agents/src/transfer.rs',
                 'research', 'benchmarks/adapters/alphazero_strength.py',
                 'benchmarks/strength/run.py', 'benchmarks/strength/REPORT.md',
                 'benchmarks/strength/PROFILES.md', 'benchmarks/strength/results']
    assert not subprocess.check_output(['git', '-C', str(ROOT), 'diff',
        frozen['base_revision'], '--', *protected], text=True).strip()
    if args.runtime:
        assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse',
                                       'HEAD'], text=True).strip() == PIN
        for name, digest in frozen['upstream_file_sha256'].items():
            assert sha(SOURCE / name) == digest, name
    index = json.loads((BASE / 'archive-index.json').read_text())
    archives = {}
    for entry in index['files']:
        path = BASE / entry['path']
        assert sha(path) == entry['gzip_sha256'], path
        digest = hashlib.sha256()
        raw_bytes = records = 0
        with gzip.open(path, 'rb') as stream:
            for line in stream:
                digest.update(line)
                raw_bytes += len(line)
                records += 1
        assert digest.hexdigest() == entry['raw_sha256'], path
        assert raw_bytes == entry['raw_bytes'], path
        assert records == entry['recorded_games'] + 1, path
        raw = path.with_suffix('')
        if raw.exists():
            assert sha(raw) == entry['raw_sha256'], raw
        archives[entry['path']] = entry
    schedules = {}
    for name, (games, master, iterations) in EXPECTED.items():
        summary = json.loads((BASE / name / 'summary.json').read_text())
        replay = json.loads((BASE / name / 'replay.json').read_text())
        archive = archives[f'{name}/games.jsonl.gz']
        assert archive['full_schedule'] and archive['recorded_games'] == games
        assert summary['games'] == replay['checked_games'] == games
        assert summary['statuses'] == {'complete': games}
        assert summary['pairing_verified'] and summary['setup_blocks'] == games // 2
        assert summary['raw_sha256'] == replay['raw_sha256'] == archive['raw_sha256']
        metadata = summary['metadata']
        assert metadata['master'] == master and metadata['iterations'] == iterations
        assert metadata['model_sha256'] == frozen['primary']['model_sha256']
        assert metadata['external_config'] == frozen['external']
        assert metadata['upstream_revision'] == PIN
        assert metadata['revision'] == frozen['repository_revision']
        assert metadata['policy_binary_sha256'] == frozen['source_model_binary_sha256'][
            'target/release/examples/native_policy_worker']
        assert replay['script_sha256'] == sha(BASE / 'replay.py')
        assert summary['source_sha256'] == sha(BASE / 'summarize.py')
        aggregate_rows = {}
        with gzip.open(BASE / f'{name}/games.jsonl.gz', 'rb') as stream:
            next(stream)
            for line in stream:
                aggregate_rows[json.loads(line)['index']] = hashlib.sha256(line).hexdigest()
        shard_rows = {}
        for shard_name in sorted(key for key in archives
                                 if key.startswith(f'{name}/shard-') and key.endswith('.jsonl.gz')):
            assert archives[shard_name]['full_schedule'], shard_name
            with gzip.open(BASE / shard_name, 'rb') as stream:
                shard_metadata = json.loads(next(stream))
                assert shard_metadata['master'] == master
                assert shard_metadata['iterations'] == iterations
                for line in stream:
                    index = json.loads(line)['index']
                    assert index not in shard_rows, index
                    shard_rows[index] = hashlib.sha256(line).hexdigest()
        assert shard_rows == aggregate_rows, ('shards differ from replayed records', name)
        schedules[name] = dict(games=games, transitions=replay['checked_transitions'],
                               raw_sha256=archive['raw_sha256'],
                               completion_rate=summary['completion_rate'],
                               exact_shard_records_verified=True)
    control_paths = {
        'smoke.jsonl.gz': 'smoke-replay.json',
        'development-native-slot-order/smoke.jsonl.gz': 'development-native-slot-order/smoke-replay.json',
        'development-native-slot-order-scaling/workers-1/shard-00.jsonl.gz':
            'development-native-slot-order-scaling/workers-1/saved-only-replay.json',
        **{f'scaling/workers-{workers}/games.jsonl.gz': f'scaling/workers-{workers}/replay.json'
           for workers in [1, 4, 8]},
    }
    controls = {}
    for archive_name, replay_name in control_paths.items():
        replay = json.loads((BASE / replay_name).read_text())
        archive = archives[archive_name]
        expected_hash = replay.get('original_raw_sha256', replay['raw_sha256'])
        assert expected_hash == archive['raw_sha256'], archive_name
        assert replay['checked_games'] == archive['recorded_games'], archive_name
        controls[archive_name] = dict(games=replay['checked_games'],
                                      transitions=replay['checked_transitions'],
                                      full_schedule=archive['full_schedule'])
    result = dict(profile=frozen['profile'], code_revision=frozen['repository_revision'],
                  upstream_revision=PIN, protected_files_unchanged=True,
                  runtime_checked=args.runtime, verified_archives=len(archives),
                  schedules=schedules, controls=controls, audit_script_sha256=sha(__file__),
                  scope='Artifact integrity and completed replay evidence; no fresh policy rerun')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
