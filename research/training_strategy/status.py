"""Read live process identity and recent work counters without changing a run."""
import argparse
import json
import subprocess
from pathlib import Path


def process(pid, expected=()):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'pid=,etime=,state=,command='],
                            capture_output=True, text=True)
    fields = result.stdout.strip().split(None, 3)
    if result.returncode != 0 or len(fields) != 4:
        return dict(pid=pid, live=False)
    command = fields[3]
    return dict(pid=pid, live=True, elapsed=fields[1], state=fields[2], command=command,
                identity_matches=all(str(part) in command for part in expected))


def read_json(path):
    # A controller can be between truncate and write while its receipt is read.
    for _ in range(3):
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
    return None


def status(directory):
    directory = Path(directory).resolve()
    root = Path(__file__).resolve().parents[2]
    controller_paths = [str(directory)]
    if directory.is_relative_to(root):
        controller_paths.append(str(directory.relative_to(root)))
    progress = read_json(directory / 'progress.json')
    if progress is None:
        raise RuntimeError('Progress receipt is being updated; check the same run again')
    result = dict(directory=str(directory), progress=progress,
                  complete=(directory / 'complete.json').exists(),
                  failure=read_json(directory / 'failure.json')
                  if (directory / 'failure.json').exists() else None,
                  controller=process(progress['pid']), commands={}, services={},
                  completed_collections={})
    controller = result['controller']
    if controller['live']:
        controller['identity_matches'] = (
            any(module in controller['command'] for module in
                ('research/training_strategy/run_', 'research/training_strategy/resume_first.py')) and
            any(path in controller['command'] for path in controller_paths))
    for path in directory.glob('*/process.json'):
        if path.with_name('exit.json').exists():
            continue
        saved = read_json(path)
        if saved:
            result['commands'][path.parent.name] = process(saved['pid'], saved['command'])
    service_paths = list(directory.glob('*-service/run.json'))
    if progress.get('recovery'):
        recovery = Path(progress['recovery']).resolve()
        assert recovery.is_relative_to(directory)
        service_paths.extend(recovery.glob('*-service/run.json'))
    for path in service_paths:
        saved = read_json(path)
        if not saved:
            continue
        service = process(saved['pid'], saved['command'])
        log = path.with_name('service.log')
        snapshots = []
        if log.exists():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 8192))
                lines = stream.read().decode('utf-8', errors='replace').splitlines()
            for line in lines:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if all(key in item for key in ('calls', 'batches', 'seconds')):
                    snapshots.append(item)
        if snapshots:
            service['latest_counter'] = snapshots[-1]
        if len(snapshots) >= 2:
            previous, latest = snapshots[-2:]
            delta = latest['seconds'] - previous['seconds']
            if delta > 0:
                service['recent_calls_per_second'] = (latest['calls'] - previous['calls']) / delta
                service['counter_interval_seconds'] = delta
        result['services'][str(path.parent.relative_to(directory))] = service
    for path in directory.glob('*/complete.json'):
        receipt = read_json(path)
        if receipt and 'games' in receipt and 'counts' in receipt:
            result['completed_collections'][path.parent.name] = {
                key: receipt[key] for key in
                ('games', 'counts', 'seconds', 'threads', 'rows', 'simulations', 'inferences')}
    result['partial_bytes'] = {str(path.relative_to(directory)): path.stat().st_size
                               for path in directory.glob('*/*.partial')}
    # A counter measures completed work. It cannot alone prove that its PID is live now.
    result['verified_live_stage_commands'] = [name for name, item in result['commands'].items()
                                             if item['live'] and item.get('identity_matches')]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(status(args.directory), indent=2))


if __name__ == '__main__':
    main()
