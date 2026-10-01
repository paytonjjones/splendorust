#!/usr/bin/env python3
"""Frozen three-arm screen and confirmation. No result-dependent settings."""
import json
import subprocess
import sys
from pathlib import Path
from boundary import ROOT, ARMS, sha
from schedule import run_schedule

BASE = Path(__file__).resolve().parent
PYTHON = ROOT/'local/strength/inference/bin/python'
MODEL = ROOT/'research/e81/model/model.bin'

def main():
    freeze = json.loads((BASE/'freeze.json').read_text())
    for name, expected in freeze['files'].items():
        assert sha(ROOT/name) == expected, ('changed frozen file', name)
    for stage, games, master in [('screen', 2000, 4900000000), ('confirmation', 20000, 4910000000)]:
        for arm in ARMS:
            directory = BASE/stage/arm
            if directory.exists():
                assert (directory/'replay.json').exists(), 'partial schedule retained; cannot silently resume'
                print('VERIFIED EXISTING', stage, arm, flush=True)
                continue
            (BASE/'progress.json').write_text(json.dumps(dict(stage=stage, arm=arm, status='running', games=games, master=master),indent=2)+'\n')
            print('START', stage, arm, games, flush=True)
            run_schedule(directory, games, master, 8, 128, MODEL, 'gumbel', False, arm)
            with (directory/'replay.log').open('w') as log:
                subprocess.run([PYTHON, BASE/'replay.py', directory/'games.jsonl', '--output', directory/'replay.json'],stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
            print('REPLAYED', stage, arm, flush=True)
        with (BASE/stage/'summary.log').open('w') as log:
            subprocess.run([PYTHON, BASE/'summarize.py', BASE/stage, '--output', BASE/stage/'summary.json'],stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
        print('STAGE COMPLETE', stage, flush=True)
    (BASE/'progress.json').write_text(json.dumps(dict(status='complete'),indent=2)+'\n')

if __name__ == '__main__': main()
