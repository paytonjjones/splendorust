#!/usr/bin/env python3
"""Replay retained completed records from an interrupted development schedule.

The original header and raw file remain unchanged. The temporary replay input
states only the number of saved records. This never marks the requested schedule
complete or turns missing games into wins.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from upstream import ROOT, sha
from schedule import PYTHON


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lines = args.input.read_text().splitlines()
    metadata = json.loads(lines[0])
    requested = metadata['games']
    recorded = len(lines) - 1
    assert 0 < recorded < requested
    metadata['games'] = recorded
    with tempfile.TemporaryDirectory(prefix='native-partial-audit-') as directory:
        replay_input = Path(directory) / 'saved-only.jsonl'
        replay_output = Path(directory) / 'replay.json'
        replay_input.write_text('\n'.join([json.dumps(metadata), *lines[1:]]) + '\n')
        command = [str(PYTHON), str(Path(__file__).with_name('replay.py')),
                   str(replay_input), '--output', str(replay_output)]
        subprocess.run(command, cwd=ROOT, check=True)
        result = json.loads(replay_output.read_text())
    result.update(original_raw_sha256=sha(args.input), requested_games=requested,
                  saved_games=recorded, missing_games=requested - recorded,
                  schedule_complete=False, excluded_from_strength_results=True,
                  audit_script_sha256=sha(__file__),
                  temporary_header_change='games set to saved record count for replay only')
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
