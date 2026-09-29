#!/usr/bin/env python3
"""Check saved native/aligned result evidence without rerunning benchmarks.

Short timing windows and unfinished games are valid reported observations. This
validator checks accounting and evidence consistency, not rule equivalence or a
portable performance claim. Exit 1 on missing, partial, or inconsistent evidence.
"""
import argparse
import collections
import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, label, positive=False):
    require(type(value) is int and value >= (1 if positive else 0), f'{label}: invalid count')
    return value


def close(actual, expected, label):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
            f'{label}: expected {expected}, got {actual}')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def bootstrap(values):
    rng = random.Random(20260928)
    medians = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(10000))
    return [medians[249], medians[9749]]


def archive(row, samples):
    path = Path(row['records_file'])
    if not path.is_absolute():
        path = ROOT / path
    compressed = path.read_bytes()
    require(hashlib.sha256(compressed).hexdigest() == row['records_archive_sha256'],
            f'{path}: compressed archive hash differs')
    raw = gzip.decompress(compressed)
    records = json.loads(raw)
    require(isinstance(records, list) and len(records) == row['count'], f'{path}: record count differs')
    require(hashlib.sha256(canonical(records)).hexdigest() == row['record_set_sha256'],
            f'{path}: normalized record-set hash differs')
    statuses = dict(collections.Counter(r['status'] for r in records))
    turns = sum(integer(r['turns'], 'archive turns') for r in records)
    require(all(set(r) == {'seed', 'status', 'turns', 'final_state'} for r in records),
            f'{path}: unexpected normalized record fields')
    require(len({r['seed'] for r in records}) == len(records), f'{path}: duplicate setup seeds')
    for record in records:
        final = record['final_state']
        require(isinstance(final, dict) and final['turns'] == record['turns'],
                f'{path}: final-state turn count differs')
        require((record['status'] == 'complete') == final['terminal'],
                f'{path}: completion disagrees with terminal state')
    for sample in samples:
        require(statuses == {k: v for k, v in sample['statuses'].items() if v},
                f'{path}: archive status totals differ')
        require(turns == sample['turns'], f'{path}: archive turn total differs')
    return {'records': len(records), 'statuses': statuses, 'turns': turns}


def check(path):
    report = json.loads(path.read_text())
    require(isinstance(report, dict), 'result is not an object')
    require(report.get('schema_version') == 1, 'unknown result schema')
    start = datetime.datetime.fromisoformat(report['started_utc'])
    finish = datetime.datetime.fromisoformat(report['finished_utc'])
    require(start.tzinfo is not None and finish.tzinfo is not None and finish >= start,
            'missing/invalid finished timestamp')
    require(not report.get('failures'), 'result reports setup or benchmark failures')
    rows = report['rows']
    require(isinstance(rows, list) and rows, 'no completed result rows')
    aligned = 'profile' in report
    if aligned:
        require(report['profile'] == 'seal256-intersection-v1', 'unknown aligned profile')
        require({v['policy'] for v in report['validation']} == {'random', 'fixed'},
                'missing random/fixed trace validation')
        require(all(v['match'] and v['cases'] > 0 for v in report['validation']), 'failed trace validation')
    thread_groups = {}
    common_groups = {}
    archives_checked = {}
    preliminary = 0
    outcomes = {}
    for index, row in enumerate(rows):
        label = f'row {index} {row.get("engine")} {row.get("workload", row.get("policy"))} t{row.get("threads")}'
        count = integer(row['count'], label + ' count', True)
        integer(row['threads'], label + ' threads', True)
        samples = row['samples']
        require(isinstance(samples, list) and samples, label + ': no repetition samples')
        summary = row['summary']
        require(summary['repetitions'] == len(samples), label + ': repetition count differs')
        seconds = []
        signatures = []
        for sample in samples:
            elapsed = sample.get('seconds', sample.get('elapsed_seconds'))
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed > 0,
                    label + ': invalid elapsed duration')
            seconds.append(elapsed)
            for key in ('count', 'games', 'iterations'):
                if key in sample:
                    require(sample[key] == count, label + ': sample workload count differs')
            if 'transitions' in sample:
                require(sample['transitions'] == count, label + ': transition count differs')
            if 'completed' in sample:
                completed = integer(sample['completed'], label + ' completed')
                if aligned:
                    statuses = sample['statuses']
                    require(all(type(k) is str for k in statuses), label + ': invalid status name')
                    require(all(integer(v, label + ' status') >= 0 for v in statuses.values()), label + ': invalid statuses')
                    require(sum(statuses.values()) == count and statuses.get('complete', 0) == completed,
                            label + ': outcome total differs')
                    allowed = {'complete', 'profile_blocked', 'no_legal_action', 'unsupported_noble_choice', 'decision_limit'}
                    require(set(statuses) <= allowed, label + ': unsupported/error outcome in aligned benchmark')
                    signatures.append((tuple(sorted((k, v) for k, v in statuses.items() if v)), sample['turns']))
                else:
                    blocked = integer(sample['blocked'], label + ' blocked')
                    capped = integer(sample['capped'], label + ' capped')
                    require(completed + blocked + capped == count, label + ': outcome total differs')
                    require(sample.get('illegal', 0) == 0, label + ': illegal transitions')
                    signatures.append(tuple(sample[k] for k in ('digest', 'decisions', 'turns', 'simulations', 'completed', 'blocked', 'capped')))
                require(completed <= count, label + ': completions exceed trajectories')
                integer(sample['turns'], label + ' turns')
                if 'decisions' in sample:
                    integer(sample['decisions'], label + ' decisions')
                if 'simulations' in sample:
                    integer(sample['simulations'], label + ' simulations')
            elif 'checksum' in sample:
                multiplier = 5 if row['engine'] == 'lyquentxy' else 1
                if row.get('workload') == 'opening_clone_take':
                    require(sample['checksum'] == multiplier * count, label + ': opening checksum differs')
                signatures.append((sample['checksum'],))
            else:
                raise ValueError(label + ': no deterministic result evidence')
        require(all(s == signatures[0] for s in signatures), label + ': outcomes/checksum vary across repetitions')
        close(summary['median_seconds'], statistics.median(seconds), label + ' median duration')
        require(len(summary['duration_range_seconds']) == 2, label + ': missing duration range')
        for actual, expected in zip(summary['duration_range_seconds'], (min(seconds), max(seconds))):
            close(actual, expected, label + ' duration range')
        rates = [count / t for t in seconds]
        rate_key = 'trajectories_per_second' if aligned else 'median_units_per_second'
        close(summary[rate_key], statistics.median(rates), label + ' throughput')
        expected_interval = bootstrap(rates)
        require(len(summary['median_rate_bootstrap95']) == 2, label + ': invalid bootstrap interval')
        for actual, expected in zip(summary['median_rate_bootstrap95'], expected_interval):
            close(actual, expected, label + ' bootstrap interval')
        short = min(seconds) < 1 or len(samples) < 7
        require(summary['timing_confidence'] == ('preliminary' if short else 'local repeated timing'),
                label + ': timing confidence mislabels short/small run')
        preliminary += short
        if 'coefficient_of_variation_seconds' in summary:
            expected = statistics.stdev(seconds) / statistics.mean(seconds) if len(seconds) > 1 else None
            if expected is None:
                require(summary['coefficient_of_variation_seconds'] is None, label + ': CV should be null')
            else:
                close(summary['coefficient_of_variation_seconds'], expected, label + ' CV')
        if 'completed' in samples[0]:
            measures = {'completed_games_per_second': 'completed', 'completed_turns_per_second': 'turns'} if aligned else {
                name + '_per_second': name for name in ('completed', 'decisions', 'turns', 'simulations')}
            for key, numerator in measures.items():
                close(summary[key], statistics.median(s[numerator] / t for s, t in zip(samples, seconds)), label + ' ' + key)
            completed_key = 'completed_games_per_second' if aligned else 'completed_per_second'
            require(summary[completed_key] <= summary[rate_key] * (1 + 1e-9), label + ': completed rate exceeds trajectory rate')
            if aligned:
                close(summary['median_setup_seconds'], statistics.median(s['setup_seconds'] for s in samples), label + ' setup duration')
            else:
                evidence = {k: samples[0][k] for k in ('digest', 'decisions', 'turns', 'completed', 'blocked', 'capped', 'simulations')}
                require(hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest() == row['record_summary_sha256'],
                        label + ': deterministic summary hash differs')
            outcomes[label] = samples[0].get('statuses', {k: samples[0][k] for k in ('completed', 'blocked', 'capped') if k in samples[0]})
        group_key = (row['engine'], row.get('workload', row.get('policy')), row.get('players'), row.get('mode'), count)
        prior = thread_groups.setdefault(group_key, signatures[0])
        require(prior == signatures[0], label + ': deterministic outcomes/checksum differ across workers')
        if aligned:
            require(row['profile'] == report['profile'], label + ': profile differs')
            group_key = (row['comparison_group'], row.get('policy'))
            signature = (count, row['corpus_sha256'], row['record_set_sha256'], signatures[0])
            require(common_groups.setdefault(group_key, signature) == signature,
                    label + ': common corpus/records differ across engines or workers')
            cache_key = (row['records_file'], row['records_archive_sha256'], row['record_set_sha256'])
            if cache_key not in archives_checked:
                archives_checked[cache_key] = archive(row, samples)
            else:
                expected = archives_checked[cache_key]
                require(expected['turns'] == samples[0]['turns'] and expected['statuses'] == {k: v for k, v in samples[0]['statuses'].items() if v},
                        label + ': shared archive totals differ')
    return {'path': str(path), 'valid': True, 'rows': len(rows), 'preliminary_rows': preliminary,
            'archives_checked': len(archives_checked), 'outcomes': outcomes,
            'scope': 'Saved accounting, repetition summaries and deterministic evidence only; no rule or host-speed proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path, help='native and/or aligned result JSON files')
    args = parser.parse_args()
    results = []
    failed = False
    for path in args.paths:
        try:
            results.append(check(path))
        except (OSError, ValueError, KeyError, TypeError, OverflowError, gzip.BadGzipFile) as error:
            failed = True
            results.append({'path': str(path), 'valid': False, 'error': str(error)})
    print(json.dumps({'valid': not failed, 'results': results}, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
