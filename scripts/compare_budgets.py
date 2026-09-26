#!/usr/bin/env python3
"""Paired fixed-iteration budget evidence; never a promotion decision."""
import argparse
import copy
import gzip
import hashlib
import json
import math
import pathlib

from collect_evidence import validate_report


def credit_bounds(record):
    if record['status'] != 'complete':
        return (0.0, 1.0)
    seat = record['seats'].index(0)
    credit = (1.0 / record['winners'].bit_count()
              if record['winners'] & (1 << seat) else 0.0)
    return credit, credit


def bounded_interval(values, alpha):
    """Two-sided empirical Bernstein for values in [-1,1]."""
    if len(values) < 2:
        return [-1.0, 1.0]
    xs = [(x + 1) / 2 for x in values]
    mean = sum(xs) / len(xs)
    variance = sum((x - mean)**2 for x in xs) / (len(xs) - 1)
    log = math.log(4 / alpha)
    half = math.sqrt(2 * variance * log / len(xs)) + 7 * log / (3 * (len(xs) - 1))
    return [2 * max(0, mean - half) - 1, 2 * min(1, mean + half) - 1]


def compare(before, after):
    for report in (before, after):
        validate_report(report)
        if not report['reproducible'] or not report.get('source_id'):
            raise ValueError('fixed budgets and a source identity are required')
    configs = [copy.deepcopy(r['run_config']) for r in (before, after)]
    budgets = [c['search'].pop('iterations') for c in configs]
    if (configs[0] != configs[1] or before['source_id'] != after['source_id']
            or before['engine'] != after['engine']):
        raise ValueError('only iteration budget may differ')
    n = before['players']
    lower, upper = [], []
    for start in range(0, len(before['records']), n):
        lo = hi = 0.0
        for a, b in zip(before['records'][start:start+n], after['records'][start:start+n]):
            if any(a[k] != b[k] for k in ('seed', 'block', 'rotation', 'seats')):
                raise ValueError('setup and seat schedules must match')
            a_lo, a_hi = credit_bounds(a)
            b_lo, b_hi = credit_bounds(b)
            lo += b_lo - a_hi
            hi += b_hi - a_lo
        lower.append(lo / n)
        upper.append(hi / n)
    uncertain = lower != upper
    alpha = 0.025 if uncertain else 0.05
    interval = [bounded_interval(lower, alpha)[0], bounded_interval(upper, alpha)[1]]
    return dict(engine=before['engine'], source_id=before['source_id'],
                iterations=budgets, games=before['requested_games'], independent_blocks=len(lower),
                mean_difference_bounds=[sum(lower)/len(lower), sum(upper)/len(upper)],
                paired_ci95=interval, unfinished_games=[r['incomplete_games'] for r in (before, after)],
                runtime_seconds=[r['runtime_seconds'] for r in (before, after)],
                method='Seat-rotation means; empirical Bernstein on differences in [-1,1]. '
                       'Unfinished credit [0,1]; separate 97.5% lower/upper intervals when uncertain. '
                       'Positive means favor the second budget. No promotion decision.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=pathlib.Path)
    parser.add_argument('after', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    reports, hashes = [], []
    for path in (args.before, args.after):
        raw = path.read_bytes()
        if path.suffix == '.gz':
            raw = gzip.decompress(raw)
        reports.append(json.loads(raw))
        hashes.append(hashlib.sha256(raw).hexdigest())
    result = compare(*reports)
    result['raw_report_sha256'] = hashes
    result['analysis_sha256'] = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
