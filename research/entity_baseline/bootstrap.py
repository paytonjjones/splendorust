"""Attach the frozen public corpus and local Python runtime to a fresh worktree."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ORIGIN = Path('/Users/payton.jones/dev/splendorust')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def attach(destination, source):
    source = source.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        assert destination.resolve() == source, f'Existing path differs: {destination}'
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source, target_is_directory=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, default=ORIGIN)
    parser.add_argument('--runtime', type=Path, default=ORIGIN / 'local/strength/inference')
    parser.add_argument('--native-upstream', action='store_true', help='Also attach the pinned native engine for native matches')
    args = parser.parse_args()
    registry = json.loads((HERE / 'expanded-data.json').read_text())
    count = 0
    for split in ('train', 'dev'):
        for entry in registry[split]:
            for field in ('source', 'context', 'inputs'):
                path = args.data_root / Path(entry[field]).relative_to(ORIGIN)
                assert sha(path) == entry[field + '_sha256'], f'Corpus hash mismatch: {path}'
                entry[field] = str(path.resolve())
                count += 1
    directory = ROOT / 'local/research/architecture-pivots'
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / 'expanded-data.json'
    serialized = json.dumps(registry, indent=2) + '\n'
    if receipt.exists():
        assert receipt.read_text() == serialized, 'An existing corpus registry differs'
    else:
        receipt.write_text(serialized)
    # Export reads these real dev positions. It does not write to this directory.
    attach(ROOT / 'local/research/e95/dev', args.data_root / 'local/research/e95/dev')
    attach(ROOT / 'local/strength/inference', args.runtime)
    if args.native_upstream:
        attach(ROOT / 'local/strength/external/alphazero',
               args.data_root / 'local/strength/external/alphazero')
    assert sha(HERE / 'model.pt') == 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'
    print(json.dumps(dict(verified_files=count, setup_counts=registry['setup_counts'],
                         corpus_manifest_sha256=sha(HERE / 'expanded-data.json'),
                         python=str(ROOT / 'local/strength/inference/bin/python'))))


if __name__ == '__main__':
    main()
