#!/usr/bin/env python3
"""Fetch pinned native references and build the interface-only C++ adapter."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import hashlib
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'seal256': ('https://github.com/seal256/splendor.git', '263abc066c563a1c89dba4bdc408446a20ad9d1d'),
    'splendimax': ('https://github.com/bouk/splendimax.git', '5ffcb148ee0093e3b47f612b04a1927301ff13ee'),
    'averagestardust': ('https://github.com/AverageStardust/splendor-engine.git', '3a85b8c8c6f050b1dcebb53820f7cf0861fcba5e'),
}

def run(args, **kwargs):
    subprocess.run(args, check=True, **kwargs)

def setup(name):
    url, commit = PINS[name]
    dest = ROOT / 'local/benchmarks/external' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    if not dest.exists():
        run(['git', 'clone', url, str(dest)])
        run(['git', '-C', str(dest), 'checkout', '--detach', commit])
    actual = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise SystemExit(f'{name}: expected {commit}, got {actual}; use an empty isolated directory')
    if name == 'seal256':
        # Compile only engine sources. No torch, network, UI, or training dependency.
        header = dest / 'src/splendor.h'
        original = subprocess.check_output(['git', '-C', str(dest), 'show', f'{commit}:src/splendor.h'], text=True)
        patched = original.replace('private:\n    std::pair<bool, ActionError> verify_action(const int action_id) const;', 'public: // Benchmark interface only: expose the unchanged validation method.\n    std::pair<bool, ActionError> verify_action(const int action_id) const;\nprivate:')
        if header.read_text() not in (original, patched):
            raise SystemExit('seal256 header has an unknown patch')
        dirty = subprocess.check_output(['git', '-C', str(dest), 'diff', '--name-only'], text=True).splitlines()
        if any(x != 'src/splendor.h' for x in dirty):
            raise SystemExit('seal256 source has an unknown patch')
        header.write_text(patched)
        binary = dest.parent / 'seal256-opening'
        run(['clang++', '-O3', '-DNDEBUG', '-std=c++17', '-pthread', '-I', str(dest / 'src'), str(ROOT / 'benchmarks/adapters/external_seal256.cpp'), str(dest / 'src/splendor.cpp'), str(dest / 'src/game_state.cpp'), '-o', str(binary)])
        run(['clang++', '-O3', '-DNDEBUG', '-std=c++17', '-pthread', '-I', str(dest / 'src'), str(ROOT / 'benchmarks/adapters/external_seal256_game.cpp'), str(dest / 'src/splendor.cpp'), str(dest / 'src/game_state.cpp'), '-o', str(dest.parent / 'seal256-game')])
    elif name == 'averagestardust':
        # This pinned binary package is for the measurement host, macOS ARM64.
        go = dest.parent / 'go/bin/go'
        if not go.exists():
            archive = dest.parent / 'go1.27.1.darwin-arm64.tar.gz'
            if not archive.exists():
                urllib.request.urlretrieve('https://go.dev/dl/go1.27.1.darwin-arm64.tar.gz', archive)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != 'ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12':
                raise SystemExit('Go archive checksum differs')
            with tarfile.open(archive) as package:
                package.extractall(dest.parent, filter='data')
        run([str(go), 'test', './...'], cwd=dest)
        binary = dest.parent / 'averagestardust-rule-probe'
        run([str(go), 'build', '-o', str(binary), str(ROOT / 'benchmarks/adapters/external_go_probe.go')], cwd=dest)
    else:
        # Cargo isolation metadata only. No rules or search code is changed.
        manifest = dest / 'Cargo.toml'
        text = manifest.read_text()
        patch = '\n# Interface build isolation only; no engine change.\n[workspace]\n'
        if '[workspace]' not in text:
            manifest.write_text(text + patch)
        (dest / 'Cargo.lock').write_bytes((ROOT / 'benchmarks/external/splendimax.Cargo.lock').read_bytes())
        run(['cargo', 'build', '--release', '--locked', '--manifest-path', str(manifest)])
        binary = dest / 'target/release/splendimax-test'
    print(json.dumps({'engine': name, 'commit': commit, 'setup_build_seconds': time.perf_counter() - start, 'binary': str(binary), 'source_patch': 'splendor.h: expose unchanged verify_action via public access only' if name == 'seal256' else ('none' if name == 'averagestardust' else 'Cargo.toml: append empty workspace table for build isolation')}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('engine', choices=PINS)
    setup(parser.parse_args().engine)
