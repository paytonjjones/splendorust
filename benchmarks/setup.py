#!/usr/bin/env python3
"""Build pinned measurement engines; installation is outside all speed timers."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def checked(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', action='store_true', help='also install isolated optimized Python adapter dependencies')
    parser.add_argument('--references', action='store_true', help='also build excluded Rust and Go rule probes')
    args = parser.parse_args()
    log = []
    def step(name, command):
        start = time.perf_counter()
        completed = checked(command, text=True, capture_output=True)
        log.append({'step': name, 'command': command, 'wall_seconds': time.perf_counter()-start,
                    'stdout': completed.stdout, 'stderr': completed.stderr})
    step('splendorust release examples', ['cargo','build','--release','--locked','-p','splendor-arena','--examples','--features','benchmark-compat'])
    for engine in ['seal256'] + (['splendimax','averagestardust'] if args.references else []):
        step(engine, ['python3','benchmarks/external/setup_native.py',engine])
    if args.references:
        manifest = json.loads((ROOT/'benchmarks/external/python_roeey.json').read_text())
        dest = ROOT/manifest['isolated_directory']
        if not dest.exists():
            step('rules reference source clone',['git','clone',manifest['url'],str(dest)])
            step('rules reference source pin',['git','-C',str(dest),'checkout','--detach',manifest['revision']])
        revision = subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
        changes = subprocess.check_output(['git','-C',str(dest),'diff','--name-only'],text=True).strip()
        if revision != manifest['revision'] or changes:
            raise RuntimeError('rules reference revision or source differs from the pinned clean checkout')
    if args.python:
        manifest = json.loads((ROOT/'benchmarks/external/python_lyquentxy.json').read_text())
        dest = ROOT/manifest['isolated_directory']
        if not dest.exists():
            step('Python source clone',['git','clone',manifest['url'],str(dest)])
            step('Python source pin',['git','-C',str(dest),'checkout','--detach',manifest['revision']])
        revision = subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
        if revision != manifest['revision']:
            raise RuntimeError(f'Python revision differs: {revision}')
        changes = subprocess.check_output(['git','-C',str(dest),'diff','--name-only'],text=True).strip()
        if changes:
            raise RuntimeError(f'Python source has local modifications: {changes}')
        interpreter = dest/'.venv/bin/python'
        if not interpreter.exists():
            step('isolated Python',['uv','venv','--python','3.12.7',str(dest/'.venv')])
        step('Python dependencies',['uv','pip','install','--python',str(interpreter),'numpy==1.26.4','numba==0.62.0','llvmlite==0.45.1','colorama==0.4.6'])
        step('Python dependency manifest',['uv','pip','freeze','--python',str(interpreter)])
    output = ROOT/'local/benchmarks/setup-metadata.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    prior = json.loads(output.read_text()) if output.exists() else None
    history = [] if prior is None else prior.get('history', []) + [{k:v for k,v in prior.items() if k != 'history'}]
    output.write_text(json.dumps({'kind':'setup/build costs; existing caches may be reused','steps':log,'history':history},indent=2)+'\n')
    print(output)


if __name__ == '__main__':
    main()
