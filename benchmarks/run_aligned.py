#!/usr/bin/env python3
"""Validate complete shared traces, then time the declared full-turn profile."""
import argparse
import gzip
import hashlib
import json
import datetime
import platform
import os
from pathlib import Path
import subprocess
import sys
import time

from make_corpus import create
from run import ROOT, fingerprint, interval, optional


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def run(engine, corpus, policy, threads, trace=False):
    exe = 'target/release/examples/aligned_worker' if engine == 'splendorust' else 'local/benchmarks/external/seal256-game'
    args = [exe, '--corpus', str(corpus), '--policy', policy, '--threads', str(threads)]
    if trace:
        args += ['--trace']
        if engine == 'splendorust':
            args += ['--check']
    start = time.perf_counter()
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=True)
    process_seconds = time.perf_counter() - start
    obj = json.loads(completed.stdout)
    if engine == 'splendorust':
        sample = obj['samples'][0]
        sample['worker_setup_seconds'] = obj['pool_startup_seconds']
    else:
        sample = obj
        sample['seconds'] = sample['elapsed_seconds']
        sample['count'] = sample['games']
        sample['turns'] = sample['main_turns']
        sample['statuses'] = {status: sum(r['status'] == status for r in sample['records']) for status in sorted(set(r['status'] for r in sample['records']))}
    sample['process_wall_seconds'] = process_seconds
    sample['timing_boundary'] = obj['timing_boundary']
    return sample


def normalized_records(sample, trace=False):
    fields = ['seed', 'status', 'turns', 'final_state']
    if trace:
        fields += ['action_keys', 'legal_keys', 'trace']
    return [{k: r[k] for k in fields} for r in sample['records']]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=7)
    parser.add_argument('--target-seconds', type=float, default=1.25)
    parser.add_argument('--max-cases', type=int, default=100000)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    assert args.repetitions >= 2 and args.max_cases >= 64 and args.threads >= 2
    external = json.loads((ROOT / 'benchmarks/external/seal256-data.json').read_text())
    report = {'schema_version': 1, 'uncertainty':{'method':'percentile bootstrap of median repetition rates', 'resamples':10000, 'seed':20260928, 'coverage':0.95}, 'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'machine': {'cpu':optional(['sysctl','-n','machdep.cpu.brand_string']), 'os':platform.platform(), 'os_build':optional(['sw_vers']), 'logical_cores':os.cpu_count(), 'physical_cores':optional(['sysctl','-n','hw.physicalcpu']), 'memory_bytes':optional(['sysctl','-n','hw.memsize']), 'power':optional(['pmset','-g','batt']), 'load_at_start':os.getloadavg()},
              'binaries_sha256': {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('target/release/examples/aligned_worker', 'local/benchmarks/external/seal256-game')},
              'interface_patch_sha256':hashlib.sha256((ROOT/'benchmarks/external/seal256-interface.patch').read_bytes()).hexdigest(),
              'external_source_status': optional(['git','-C','local/benchmarks/external/seal256','status','--short']),
              'setup_build':json.loads((ROOT/'local/benchmarks/setup-metadata.json').read_text()),
              'versions': {'rust':optional(['rustc','-Vv']), 'cpp':optional(['clang++','--version'])},
              'sources': {'splendorust_status':optional(['git','status','--short']), 'splendorust_commit':optional(['git','rev-parse','HEAD']), 'seal256_commit':optional(['git','-C','local/benchmarks/external/seal256','rev-parse','HEAD'])},
              'build_flags': {'rust':'release opt-level3, thinLTO, codegen-units1; benchmark-compat feature', 'cpp':'-O3 -DNDEBUG -std=c++17 -pthread', 'env':{key:os.environ.get(key) for key in ('RUSTFLAGS','CXXFLAGS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')}},
              'command':sys.argv,
 'profile': 'seal256-intersection-v1', 'protocol': 'benchmarks/PROFILES.md', 'profile_contract_sha256':hashlib.sha256((ROOT/'benchmarks/PROFILES.md').read_bytes()).hexdigest(),
              'suite_source_sha256': fingerprint(), 'validation': [], 'rows': [],
              'notes': ['Same injected card/noble setup, semantic main action keys, SplitMix64 streams and policy.',
                        'Native decisions differ: Rust payment phases and C++ chance refills. Rank common completed turns and trajectories, not native decisions.',
                        'Each measured repetition uses an identical case corpus. Alternate full engine/worker order.',
                        'Setup is serial and outside gameplay timer. Process time includes parsing, warmup, setup, gameplay, snapshots and serialization.',
                        'Incomplete profile cases stay in every throughput denominator; none gets a victory.',
                        'Per-game latency clocks are inside this workload; snapshot extraction is outside gameplay.',
                        'This profile restricts policy choices, and stops unsupported multi-noble buys. It is not all published legal play.',
                        'C++ minimal JSON record boxing is timed; Rust uses a typed record. Full snapshots and serialization are excluded.']}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    smoke = ROOT / 'benchmarks/fixtures/aligned-smoke.json'
    for policy in ('random', 'fixed'):
        print(f'trace validation {policy}', flush=True)
        a = run('splendorust', smoke, policy, 1, True)
        b = run('seal256', smoke, policy, 1, True)
        ar, br = normalized_records(a, True), normalized_records(b, True)
        if ar != br:
            failure = args.output.parent / f'{args.output.stem}-alignment-failure-{policy}-{time.time_ns()}.json.gz'
            failure.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(failure, 'wb') as file:
                file.write(encode({'splendorust': ar, 'seal256': br}))
            raise RuntimeError(f'trace mismatch: {failure}')
        report['validation'].append({'policy': policy, 'cases': a['count'], 'turns': a['turns'], 'statuses': a['statuses'],
                                     'trace_and_legal_sets_sha256': hashlib.sha256(encode(ar)).hexdigest(), 'match': True})
        save()
    pilot_path = ROOT / 'local/benchmarks/aligned-pilot.json'
    pilot_path.parent.mkdir(parents=True, exist_ok=True)
    pilot_path.write_bytes(encode(create(1024, 940000001, external)))
    import statistics
    for policy in ('random', 'fixed'):
        pilots = {engine: run(engine, pilot_path, policy, args.threads) for engine in ('splendorust', 'seal256')}
        pilot = min(pilots.values(), key=lambda sample: sample['seconds'])
        count = min(args.max_cases, max(1024, int(1024 * args.target_seconds / pilot['seconds'] * 1.15)))
        corpus = ROOT / f'local/benchmarks/aligned-{policy}.json'
        corpus.write_bytes(encode(create(count, 950000001, external)))
        corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest()
        configs = [{'engine': engine, 'policy': policy, 'threads': threads, 'count': count, 'corpus_sha256': corpus_hash,
                    'corpus_master_seed': 950000001, 'pilot_seconds': pilot['seconds'], 'pilot_threads': args.threads, 'pilots_seconds':{engine:sample['seconds'] for engine,sample in pilots.items()}, 'samples': [],
                    'comparison_group': f'aligned-{policy}-2p', 'profile': report['profile']} for engine in ('splendorust', 'seal256') for threads in (1, args.threads)]
        report['rows'].extend(configs)
        expected_hash = None
        for rep in range(args.repetitions):
            for row in (configs if rep % 2 == 0 else list(reversed(configs))):
                print(f"aligned {policy} {row['engine']} t{row['threads']} rep{rep+1} cases{count}", flush=True)
                sample = run(row['engine'], corpus, policy, row['threads'])
                records = normalized_records(sample)
                digest = hashlib.sha256(encode(records)).hexdigest()
                if expected_hash is None:
                    expected_hash = digest
                assert digest == expected_hash, f"record mismatch in {row['engine']} t{row['threads']}"
                assert sample['completed'] + sum(v for k,v in sample['statuses'].items() if k != 'complete') == count
                if rep == 0:
                    file_path = args.output.parent.resolve() / f"{args.output.stem}-{policy}-{corpus_hash[:16]}-records.json.gz"
                    if row['engine'] == 'splendorust' and row['threads'] == 1:
                        with gzip.open(file_path, 'wb') as file:
                            file.write(encode(records))
                    row['records_file'] = os.path.relpath(file_path, ROOT)
                    row['records_archive_sha256'] = hashlib.sha256(file_path.read_bytes()).hexdigest()
                    # Direct latency percentiles from the first repetition; split outcomes.
                    row['latency_seconds'] = {}
                    for status in ('all', 'complete', 'unfinished'):
                        values = sorted(r['latency_seconds'] for r in sample['records'] if status == 'all' or (r['status'] == 'complete') == (status == 'complete'))
                        row['latency_seconds'][status] = {'count': len(values), **({f'p{int(p*100)}': values[int((len(values)-1)*p)] for p in (.5, .95, .99)} if values else {})}
                row['samples'].append({k:v for k,v in sample.items() if k not in ('records', 'samples')})
                row['record_set_sha256'] = digest
                save()
        for row in configs:
            samples = row['samples']
            times = [x['seconds'] for x in samples]
            rates = [count / t for t in times]
            row['summary'] = {'median_seconds': statistics.median(times), 'duration_range_seconds': [min(times), max(times)],
                              'trajectories_per_second': statistics.median(rates), 'median_rate_bootstrap95': interval(rates),
                              'completed_games_per_second': statistics.median(x['completed']/x['seconds'] for x in samples),
                              'completed_turns_per_second': statistics.median(x['turns']/x['seconds'] for x in samples),
                              'median_setup_seconds': statistics.median(x['setup_seconds'] for x in samples),
                              'repetitions': len(samples), 'timing_confidence': 'preliminary' if min(times) < 1 or len(samples) < 7 else 'local repeated timing'}
            # Rows were added before timing so partial failures retain samples.
        save()
    report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['machine']['load_at_finish'] = os.getloadavg()
    save()
    print(args.output, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        path = ROOT / f'benchmarks/results/aligned-run-failure-{time.time_ns()}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'error': str(error), 'argv': sys.argv}, indent=2) + '\n')
        raise
