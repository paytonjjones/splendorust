#!/usr/bin/env python3
"""Reassess preserved gate evidence under P2; never replace a game or old decision."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from promote import (DEFAULT_MAX_NO_ACTION_FRACTION, checked_interval,
                     completion_evidence, decision, validate_stage)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reassess(directory, max_no_action_fraction=DEFAULT_MAX_NO_ACTION_FRACTION):
    directory = Path(directory).resolve()
    old_path, run_path = directory/'decision.json', directory/'run.json'
    old, run = json.loads(old_path.read_bytes()), json.loads(run_path.read_bytes())
    if old.get('stage') not in ('screen', 'confirm') or 'raw_report_sha256' not in old:
        raise ValueError('execution failures cannot be reassessed as strength evidence')
    report_path = directory/f"{old['stage']}.json"
    if sha(report_path) != old['raw_report_sha256']:
        raise ValueError('original decision and raw report hashes disagree')
    report = json.loads(report_path.read_bytes())
    interval = checked_interval(report, run['players'])
    args = SimpleNamespace(**run)
    source = None
    if old['stage'] == 'confirm':
        screen = json.loads((directory/'screen.json').read_bytes())
        checked_interval(screen, run['players'])
        source = validate_stage(screen, args, run['screen'], run['seed'], None)
    games = run[old['stage']]
    seed = run['seed'] + (1_000_000_000 if old['stage'] == 'confirm' else 0)
    validate_stage(report, args, games, seed, source)
    records_sha = hashlib.sha256(json.dumps(report['records'], sort_keys=True,
                                           separators=(',', ':')).encode()).hexdigest()
    if records_sha != old['record_set_sha256']:
        raise ValueError('original decision and record-set hashes disagree')
    result = decision(report, run['players'], run['margin'], run['min_games_per_second'],
                      max_no_action_fraction)
    if old['stage'] == 'screen' and run['confirm'] and not result.startswith('reject'):
        result = ('reject: screening shows regression' if interval[1] < 1/run['players']
                  else 'eligible for fresh confirmation; not a completed confirmation')
    return dict(analysis='Retrospective policy reassessment; original evidence is unchanged.',
                original_directory=str(directory), original_decision=old['decision'],
                original_decision_sha256=sha(old_path), original_run_sha256=sha(run_path),
                raw_report_sha256=sha(report_path), record_set_sha256=records_sha,
                source_id=report['source_id'], stage=old['stage'], decision=result,
                interval_from_records=interval, margin=run['margin'],
                minimum_games_per_second=run['min_games_per_second'],
                completion=completion_evidence(report, max_no_action_fraction),
                evidence_tools_sha256={name:sha(Path(__file__).with_name(name))
                                       for name in ('promote.py', 'collect_evidence.py', 'reassess_promotion.py')},
                champion_changed=False, new_games=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='preserved promotion run directory')
    parser.add_argument('--output', type=Path, required=True, help='new reassessment file')
    parser.add_argument('--max-no-action-fraction', type=float, default=DEFAULT_MAX_NO_ACTION_FRACTION)
    args = parser.parse_args()
    result = reassess(args.input, args.max_no_action_fraction)
    # Exclusive creation also protects input files if --output refers to one.
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2)+'\n')
    print(result['decision'])


if __name__ == '__main__':
    main()
