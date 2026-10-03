"""Restore only the first candidate and attach existing local assets on request.

This command does not start a service, game, trainer, or campaign clock.
It checks the original archive manifest and every selected byte.
"""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = Path('/Users/payton.jones/dev/splendorust')
sys.path.insert(0, str(ROOT / 'research/training_strategy'))
from archive_results import safe_path, sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


def restore_member(archive, entry, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.stat().st_size == entry['bytes'] and sha(target) == entry['sha256'],
                f'Existing artifact differs: {target}')
        return
    partial = target.with_name(target.name + '.partial')
    digest = hashlib.sha256()
    total = 0
    with partial.open('xb') as destination:
        for chunk in entry['chunks']:
            source = safe_path(archive, chunk['path'])
            require(sha(source) == chunk['compressed_sha256'], f'Corrupt chunk: {source}')
            count = 0
            chunk_digest = hashlib.sha256()
            with gzip.open(source, 'rb') as compressed:
                for block in iter(lambda: compressed.read(4 << 20), b''):
                    count += len(block)
                    require(count <= chunk['bytes'], f'Chunk size differs: {source}')
                    chunk_digest.update(block)
                    digest.update(block)
                    destination.write(block)
            require(count == chunk['bytes'] and chunk_digest.hexdigest() == chunk['uncompressed_sha256'],
                    f'Chunk content differs: {source}')
            total += count
    require(total == entry['bytes'] and digest.hexdigest() == entry['sha256'],
            f'Artifact content differs: {target}')
    partial.rename(target)


def attach(destination, source):
    source = source.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        require(destination.resolve() == source, f'Existing link differs: {destination}')
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source, target_is_directory=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'local/research/sprint48/ready')
    parser.add_argument('--attach-assets', action='store_true')
    parser.add_argument('--assets-root', type=Path, default=ORIGIN)
    parser.add_argument('--runtime', type=Path)
    args = parser.parse_args()
    plan = json.loads((ROOT / 'research/sprint48/PLAN.json').read_text())
    baseline = json.loads((ROOT / 'research/STRENGTH_CHAMPION.json').read_text())
    candidate = plan['first_candidate']
    archive = ROOT / candidate['archive']
    require(sha(archive / 'manifest.json') == candidate['archive_manifest_sha256'],
            'Archive manifest differs from the plan')
    manifest = json.loads((archive / 'manifest.json').read_text())
    entries = {entry['path']: entry for entry in manifest['files']}
    require(len(entries) == len(manifest['files']), 'Duplicate archive member')
    parent = ROOT / baseline['checkpoint']
    require(sha(parent) == baseline['checkpoint_sha256'], 'Strength baseline differs')
    for member, expected in ((candidate['checkpoint_member'], candidate['checkpoint_sha256']),
                             (candidate['runtime_member'], candidate['runtime_sha256'])):
        require(entries[member]['sha256'] == expected, f'Candidate identity differs: {member}')

    # Attach only export fixtures and runtime assets. The full 408-file corpus
    # bootstrap belongs to a training branch, not to checkpoint preparation.
    links = []
    if args.attach_assets:
        runtime = (args.runtime or args.assets_root / 'local/strength/inference').resolve(strict=True)
        require((runtime / 'bin/python').is_file(), 'Missing pinned Python environment')
        upstream = (args.assets_root / 'local/strength/external/alphazero').resolve(strict=True)
        revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True).strip()
        require(revision == plan['target']['revision'] and not dirty, 'Require pinned clean AlphaZero source')
        require(sha(upstream / 'splendor/pretrained_2players.pt') == plan['target']['checkpoint_sha256'],
                'AlphaZero weights differ')
        registry = json.loads((ROOT / 'research/entity_baseline/expanded-data.json').read_text())
        fixture = next(e for e in registry['dev'] if e['native'] and '/dev/000000/' in e['source'])
        for field in ('source', 'context'):
            source = args.assets_root / Path(fixture[field]).relative_to(ORIGIN)
            require(sha(source) == fixture[field + '_sha256'], f'Export fixture differs: {source}')
        links = [
            (ROOT / 'local/strength/inference', runtime),
            (ROOT / 'local/strength/external/alphazero', upstream),
            (ROOT / 'local/research/e95/dev', args.assets_root / 'local/research/e95/dev'),
        ]
        for destination, source in links:
            source.resolve(strict=True)
            if destination.exists() or destination.is_symlink():
                require(destination.resolve() == source.resolve(), f'Existing link differs: {destination}')

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'baseline/model.pt'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(sha(target) == baseline['checkpoint_sha256'], f'Existing artifact differs: {target}')
    else:
        shutil.copyfile(parent, target)
        require(sha(target) == baseline['checkpoint_sha256'], 'Baseline copy differs')
    members = [candidate['checkpoint_member'], candidate['runtime_member'],
               'first/onehot/manifest.json', 'first/onehot/plan.json']
    for member in members:
        restore_member(archive, entries[member], safe_path(out, member))
    for destination, source in links:
        attach(destination, source)
    receipt = dict(schema='sprint48-preparation-v1', archive_manifest_sha256=sha(archive / 'manifest.json'),
                   baseline=str(target), baseline_sha256=sha(target),
                   candidate=str(out / candidate['runtime_member']),
                   candidate_sha256=sha(out / candidate['runtime_member']),
                   restored_files={member: entries[member]['sha256'] for member in members},
                   links={str(a): str(b.resolve()) for a, b in links},
                   note='Selected artifacts only; no training corpus restoration or research job started.')
    (out / 'ready.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
