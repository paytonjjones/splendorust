"""Inventory actual cost receipts without double-counting copied evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                   separators=(',', ':')).encode()).hexdigest()


def elapsed(value):
    seconds = float(value)
    assert math.isfinite(seconds) and seconds >= 0
    return seconds


def inventory(directories):
    commands, services = {}, {}
    for directory in map(Path, directories):
        assert directory.is_dir(), f'Missing evidence directory: {directory}'
        for path in sorted(directory.rglob('process.json')):
            if not path.is_file():
                continue
            process = read(path)
            key = identity(process)
            item = commands.setdefault(key, dict(process=process, receipt_locations=[],
                exit_receipts=[], collection_receipts=[]))
            item['receipt_locations'].append(str(path))
            exit_path = path.with_name('exit.json')
            if exit_path.exists():
                receipt = read(exit_path)
                elapsed(receipt['seconds'])
                item['exit_receipts'].append(dict(path=str(exit_path), receipt=receipt))
            command = process['command']
            if '--output' in command and 'rich_selfplay' in Path(command[0]).name:
                output = Path(command[command.index('--output') + 1])
                # This is the retained original command path, not a restore path.
                completion = output / 'complete.json'
                if completion.exists():
                    receipt = read(completion)
                    elapsed(receipt['seconds'])
                    item['collection_receipts'].append(dict(path=str(completion), receipt=receipt))
        for path in sorted(directory.rglob('run.json')):
            if not path.is_file():
                continue
            log = path.with_name('service.log')
            if not log.exists():
                continue
            run = read(path)
            key = identity(run)
            item = services.setdefault(key, dict(run=run, receipt_locations=[],
                last_logged_counter=None))
            item['receipt_locations'].append(str(path))
            counter = None
            for line in log.read_text().splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if all(field in value for field in ('calls', 'batches', 'seconds')):
                    elapsed(value['seconds'])
                    if counter is not None:
                        assert value['calls'] >= counter['calls']
                        assert value['batches'] >= counter['batches']
                        assert value['seconds'] >= counter['seconds']
                    counter = value
            old = item['last_logged_counter']
            if counter is not None and (old is None or counter['seconds'] > old['seconds']):
                item['last_logged_counter'] = counter
                item['counter_log'] = str(log)

    known = 0.0
    adopted = 0.0
    unknown = []
    for key, item in commands.items():
        exits = item['exit_receipts']
        if exits:
            assert len({identity(x['receipt']) for x in exits}) == 1, 'Conflicting copied exits'
            item['returncode'] = exits[0]['receipt']['returncode']
            item['command_elapsed_seconds'] = elapsed(exits[0]['receipt']['seconds'])
            known += item['command_elapsed_seconds']
        else:
            item['returncode'] = None
            item['command_elapsed_seconds'] = None
            unknown.append(key)
            receipts = item['collection_receipts']
            if receipts:
                assert len({identity(x['receipt']) for x in receipts}) == 1
                item['collector_reported_seconds'] = elapsed(receipts[0]['receipt']['seconds'])
                adopted += item['collector_reported_seconds']

    return dict(schema='training-strategy-cost-inventory-v1', full_goal_complete=False,
        commands=commands, services=services,
        known_command_elapsed_seconds=known,
        collector_reported_seconds_without_command_exit=adopted,
        commands_without_exit_receipts=unknown,
        limits=[
            'Copied process and service receipts count once by their full receipt identity.',
            'Command elapsed seconds can overlap; their sum is not total host wall time.',
            'Collector-reported seconds are separate when the parent exit receipt is absent.',
            'Missing exit receipts do not establish failure or a successful process exit.',
            'Last logged service counters are lower bounds and are not added to command time.',
            'This inventory does not measure isolated GPU time, energy or FLOPs.',
            'Receipt inventory is not a corpus, weight or strength validity check.',
            'Final accounting must also retain archive/restore costs and interruption observations.',
        ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inventory(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('commands', 'services', 'limits')}, indent=2))


if __name__ == '__main__':
    main()
