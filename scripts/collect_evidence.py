#!/usr/bin/env python3
"""Archive reports without deleting or replacing prior experiment evidence."""
import argparse
import gzip
import hashlib
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def interval(xs):
    if len(xs) < 2:
        return [0, 1]
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean)**2 for x in xs) / (n - 1)
    log = math.log(4 / 0.05)
    half = math.sqrt(2 * var * log / n) + 7 * log / (3 * (n - 1))
    return [max(0, mean - half), min(1, mean + half)]


def validate_report(report):
    """Require complete ordered seat blocks before computing an interval."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    n = report['players']
    games = report['requested_games']
    records = report['records']
    require(type(n) is int and 2 <= n <= 4, 'invalid player count')
    require(type(games) is int and games > 0 and games % n == 0, 'incomplete requested seat blocks')
    require(len(records) == games, 'record count differs from requested games')
    require(report['independent_blocks'] == games // n, 'setup-block count differs')
    require(sorted(a['identity'] for a in report['agents']) == list(range(n)), 'invalid agent identities')
    completed = 0
    seeds = set()
    for i, game in enumerate(records):
        block, rotation = divmod(i, n)
        require(game['block'] == block and game['rotation'] == rotation, 'unordered or incomplete seat block')
        require(game['seats'] == [(seat + rotation) % n for seat in range(n)], 'invalid seat rotation')
        require(type(game['seed']) is int and 0 <= game['seed'] < 2**64, 'invalid setup seed')
        require(game['seed'] == records[block*n]['seed'], 'setup seed differs within a block')
        if rotation == 0:
            require(game['seed'] not in seeds, 'repeated setup counted as an independent block')
            seeds.add(game['seed'])
        require(game['status'] in ('complete', 'no_legal_action', 'decision_limit'), 'unknown game status')
        require(len(game['scores']) == len(game['ranks']) == n, 'invalid player result count')
        require(all(type(x) is int and 0 <= x <= 255 for x in game['scores']), 'invalid score')
        if game['status'] == 'complete':
            completed += 1
            require(all(type(rank) is int and 1 <= rank <= n for rank in game['ranks']), 'invalid normal ranks')
            winners = sum(1 << seat for seat, rank in enumerate(game['ranks']) if rank == 1)
            require(winners != 0 and game['winners'] == winners, 'winners and ranks disagree')
        else:
            require(game['winners'] == 0 and game['ranks'] == [0]*n, 'unfinished game has a winner or rank')
    require(report['completed_games'] == completed and report['incomplete_games'] == games-completed,
            'completion totals differ from records')


def summarize(raw, name):
    report = json.loads(raw)
    validate_report(report)
    records = report.pop('records')
    n = report['players']
    for agent in report['agents']:
        def credits(unknown):
            result = []
            for start in range(0, len(records), n):
                total = 0
                for game in records[start:start+n]:
                    if game['status'] != 'complete':
                        total += unknown
                        continue
                    seat = game['seats'].index(agent['identity'])
                    if game['winners'] & (1 << seat):
                        total += 1 / game['winners'].bit_count()
                result.append(total / n)
            return result
        agent['ci95'] = [interval(credits(0))[0], interval(credits(1))[1]]
    report['ci_method'] = 'Two-sided 95% empirical Bernstein over setup blocks, alpha/2 per tail; missing outcomes bounded by 0 and 1'
    report['raw_report_sha256'] = hashlib.sha256(raw).hexdigest()
    report['record_set_sha256'] = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    report['raw_archive'] = name + '.json.gz'
    report['summary_note'] = 'Intervals recomputed by scripts/collect_evidence.py; raw historical reports preserved unchanged.'
    report['status_counts'] = {key: sum(g['status'] == key for g in records) for key in sorted({g['status'] for g in records})}
    entry = {'name': name, 'games': report['requested_games'], 'completed': report['completed_games'],
             'seed': report['seed'], 'players': n, 'candidate': report['agents'][0]['agent'],
             'opponent': report['agents'][1]['agent'], 'credit': report['agents'][0]['win_rate'],
             'ci95': report['agents'][0]['ci95'], 'seconds': report['runtime_seconds'],
             'records_sha256': report['record_set_sha256']}
    return report, entry


def collect(paths, output):
    """Preflight the whole batch; retain existing index entries and raw reports."""
    index_path = output / 'index.json'
    previous = json.loads(index_path.read_text()) if index_path.exists() else []
    index = {entry['name']: entry for entry in previous}
    if len(index) != len(previous):
        raise ValueError('existing index contains duplicate names')
    pending = {}
    for path in sorted(paths):
        raw = path.read_bytes()
        if 'records' not in json.loads(raw):
            continue
        name = ('promotion-' if path.parent.name == 'promotion' else '') + path.stem
        archive = output / (name + '.json.gz')
        if name in pending:
            raise ValueError(f'duplicate report name: {name}')
        if archive.exists() and gzip.decompress(archive.read_bytes()) != raw:
            raise FileExistsError(f'archive differs: {archive}; use a new experiment name')
        report, entry = summarize(raw, name)
        if name in index and index[name]['records_sha256'] != entry['records_sha256']:
            raise FileExistsError(f'index differs: {name}; use a new experiment name')
        pending[name] = (raw, report)
        index[name] = entry
    if not pending:
        return 0
    output.mkdir(parents=True, exist_ok=True)
    for name, (raw, report) in pending.items():
        archive = output / (name + '.json.gz')
        if not archive.exists():
            archive.write_bytes(gzip.compress(raw, mtime=0))
        (output / (name + '.summary.json')).write_text(json.dumps(report, indent=2) + '\n')
    index_path.write_text(json.dumps([index[name] for name in sorted(index)], indent=2) + '\n')
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=pathlib.Path, default=ROOT / 'results')
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'docs/results')
    args = parser.parse_args()
    paths = list(args.input.glob('*.json')) + list((args.input / 'promotion').glob('*.json'))
    count = collect(paths, args.output)
    print(f'Archived {count} reports. Prior evidence retained.')


if __name__ == '__main__':
    main()
