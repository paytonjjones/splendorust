#!/usr/bin/env python3
"""Sequential benchmark orchestrator; external setup is separate and pinned."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SEED = 910000001


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def optional(args):
    try:
        return command(args)
    except (OSError, subprocess.CalledProcessError) as error:
        return str(error)


def fingerprint():
    digest = hashlib.sha256()
    paths = list((ROOT / 'crates').rglob('*.rs')) + list((ROOT / 'crates').rglob('Cargo.toml')) + list((ROOT / 'benchmarks').rglob('*.py'))
    paths += list((ROOT / 'benchmarks/adapters').glob('*.cpp')) + list((ROOT / 'benchmarks/adapters').glob('*.go'))
    paths += [ROOT / x for x in ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml')]
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class Worker:
    def __init__(self, threads):
        started = time.perf_counter()
        self.process = subprocess.Popen([str(ROOT / 'target/release/examples/benchmark_worker'), str(threads)],
                                        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.ready = json.loads(self.process.stdout.readline())
        assert self.ready['ready']
        self.startup_seconds = time.perf_counter() - started

    def run(self, request):
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f'worker failed: {self.process.poll()}')
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=30) == 0


def interval(values):
    # Deterministic percentile bootstrap over timing repetitions, not game outcomes.
    rng = random.Random(20260928)
    medians = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(10000))
    return [medians[249], medians[9749]]


def summary(row):
    samples = row['samples']
    seconds = [s.get('seconds', s.get('elapsed_seconds')) for s in samples]
    numerator = row['count']
    rates = [numerator / t for t in seconds]
    row['summary'] = {'median_seconds': statistics.median(seconds),
                      'duration_range_seconds': [min(seconds), max(seconds)],
                      'median_units_per_second': statistics.median(rates),
                      'median_rate_bootstrap95': interval(rates),
                      'repetitions': len(samples),
                      'timing_confidence': 'preliminary' if len(samples) < 7 or min(seconds) < 1 else 'local repeated timing',
                      'coefficient_of_variation_seconds': statistics.stdev(seconds) / statistics.mean(seconds) if len(seconds) > 1 else None}
    if 'completed' in samples[0]:
        for name in ('completed', 'decisions', 'turns', 'simulations'):
            row['summary'][name + '_per_second'] = statistics.median(s[name] / s['seconds'] for s in samples)
        assert all((s['digest'], s['decisions'], s['turns'], s['simulations'], s['completed'], s['blocked'], s['capped']) ==
                   (samples[0]['digest'], samples[0]['decisions'], samples[0]['turns'], samples[0]['simulations'], samples[0]['completed'], samples[0]['blocked'], samples[0]['capped']) for s in samples)
        assert samples[0]['completed'] + samples[0]['blocked'] + samples[0]['capped'] == numerator
        row['record_summary_sha256'] = hashlib.sha256(json.dumps({k: samples[0][k] for k in
            ('digest', 'decisions', 'turns', 'completed', 'blocked', 'capped', 'simulations')}, sort_keys=True).encode()).hexdigest()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=7)
    parser.add_argument('--target-seconds', type=float, default=1.25)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--skip-python', action='store_true')
    args = parser.parse_args()
    if args.repetitions < 2 or args.target_seconds <= 0 or args.threads < 2:
        parser.error('need >=2 repetitions, positive target duration and >=2 threads')
    rows = []
    report = {'schema_version': 1, 'uncertainty':{'method':'percentile bootstrap of median repetition rates', 'resamples':10000, 'seed':20260928, 'coverage':0.95}, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'protocol': 'benchmarks/PROTOCOL.md', 'protocol_sha256':hashlib.sha256((ROOT/'benchmarks/PROTOCOL.md').read_bytes()).hexdigest(), 'command':__import__('sys').argv, 'seed': SEED, 'decision_cap': 20000, 'search_config': {'iterations':128, 'depth_turns':8, 'width':6, 'rollout':'strong', 'evaluation':'engine', 'time_budget':None, 'opponents':'Strong in all other seats', 'search_seat':0}, 'repetition_order': 'alternating 1 and N workers per native configuration',
              'machine': {'cpu': optional(['sysctl', '-n', 'machdep.cpu.brand_string']),
                          'physical_cores': optional(['sysctl', '-n', 'hw.physicalcpu']),
                          'logical_cores': os.cpu_count(), 'os': platform.platform(),
                          'os_build': optional(['sw_vers']), 'memory_bytes': optional(['sysctl', '-n', 'hw.memsize']),
                          'power': optional(['pmset', '-g', 'batt']), 'load_at_start': os.getloadavg()},
              'versions': {'rust': command(['rustc', '-Vv']), 'cpp': command(['clang++', '--version']), 'runner_python': platform.python_version()},
              'build': {'rust': 'cargo build --release --locked -p splendor-arena --examples --features benchmark-compat; thin LTO, codegen-units=1; no RUSTFLAGS override',
                        'cpp': 'clang++ -O3 -DNDEBUG -std=c++17 -pthread; no CPU target flag; no LTO',
                        'env': {k: os.environ.get(k) for k in ('RUSTFLAGS', 'CXXFLAGS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')}},
              'data_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'data').glob('*.csv')},
              'binaries_sha256': {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('target/release/examples/benchmark_worker', 'local/benchmarks/external/seal256-opening')},
              'external_source_status': optional(['git','-C','local/benchmarks/external/seal256','status','--short']),
              'interface_patch_sha256':hashlib.sha256((ROOT/'benchmarks/external/seal256-interface.patch').read_bytes()).hexdigest(),
              'source': {'commit': command(['git', 'rev-parse', 'HEAD']), 'status': command(['git', 'status', '--short']), 'suite_and_rust_sha256': fingerprint()},
              'rows': rows, 'failures': [],
              'limitations': ['Shared macOS host; no core affinity or frequency lock; other processes may run.',
                              'Bootstrap intervals describe repetition noise only. Native full-choice games have no cross-engine ranking here; the separate aligned result ranks only its declared restricted profile.',
                              'Machine health and load readings do not prove an idle host.',
                              'Opening fixtures have native seeded decks; only the token transition equivalence class is compared.']}
    workers = {t: Worker(t) for t in (1, args.threads)}
    report['worker_startup'] = {str(t): {'seconds': w.startup_seconds, 'ready': w.ready} for t, w in workers.items()}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        for workload, players, pilot_count in [('setup', 2, 10000)] + [
            ('random', n, 10000) for n in (2, 3, 4)] + [('greedy', 2, 1000)] + [('search128_strong', n, 20) for n in (2, 3, 4)]:
            print(f'validate/calibrate {workload} p{players}', flush=True)
            request = {'workload': workload, 'players': players, 'seed': SEED}
            if workload in ('random', 'greedy', 'search128_strong'):
                smoke = workers[1].run(dict(request, count=20, check=True))
                smoke_parallel = workers[args.threads].run(dict(request, count=20, check=True))
                assert smoke['digest'] == smoke_parallel['digest'] and smoke['decisions'] == smoke_parallel['decisions']
                assert smoke['illegal'] == 0
            pilot = workers[args.threads].run(dict(request, count=pilot_count))
            count = max(pilot_count, math.ceil(pilot_count * args.target_seconds / pilot['seconds'] * 1.15))
            config_rows = {}
            for threads in workers:
                config_rows[threads] = {'engine': 'splendorust', 'workload': workload, 'players': players,
                    'threads': threads, 'parallelism': 'persistent Rayon thread pool', 'count': count,
                    'unit': 'cloned validated take transitions' if workload == 'opening_clone_take' else 'setups with market observation' if workload == 'setup' else 'trajectories',
                    'category':'setup' if workload == 'setup' else 'engine' if workload == 'random' else 'AI policy/search',
                    'comparable': False, 'non_comparable_reason':'Native-only workload; no equivalent external adapter measured',
                    'comparison_group': 'checked-opening-copy-take' if workload == 'opening_clone_take' else f'splendorust-only-{workload}-p{players}',
                    'pilot': pilot, 'samples': [], 'seed_schedule': 'setup=master_seed+global_index (no extra seed mix)' if workload == 'setup' else 'setup=SplitMix64(master_seed+global_index).next_u64(); policy=setup XOR 0xd1b54a32d192ed03; Search uses policy seed (seat0); Strong is deterministic'}
                workers[threads].run(dict(request, count=min(count, pilot_count))) # untimed warm-up
            rows.extend(config_rows.values())
            save()
            for rep in range(args.repetitions):
                for threads in ((1, args.threads) if rep % 2 == 0 else (args.threads, 1)):
                    config_rows[threads]['samples'].append(workers[threads].run(dict(request, count=count)))
                    save()
                    print(f'  rep{rep+1} t{threads}', flush=True)
            if workload in ('random', 'greedy', 'search128_strong'):
                assert config_rows[1]['samples'][0]['digest'] == config_rows[args.threads]['samples'][0]['digest']
                latency_count = 100 if workload == 'search128_strong' else 1000
                for threads in workers:
                    config_rows[threads]['latency_probe'] = workers[threads].run(dict(request, count=latency_count, latency=True))
                    config_rows[threads]['latency_probe']['note'] = 'Separate instrumented sample; per-trajectory setup/play, excludes final digest and queue wait. Does not replace throughput timing.'
            for row in config_rows.values():
                summary(row)
            save()
    finally:
        for worker in workers.values():
            worker.close()
    # Keep the checked comparison engines in one interleaved experiment.
    cpp = ROOT / 'local/benchmarks/external/seal256-opening'
    common_workers = {t: Worker(t) for t in (1, args.threads)}
    configurations = []
    try:
        for engine in ('splendorust', 'seal256'):
            if engine == 'seal256' and not cpp.exists():
                raise RuntimeError('run pinned C++ setup before benchmark')
            def execute(threads, count):
                if engine == 'splendorust':
                    return common_workers[threads].run({'workload': 'opening_clone_take', 'players': 2, 'count': count})
                return json.loads(command([str(cpp), '--threads', str(threads), '--seed', '12345', '--iterations', str(count)]))
            pilot_count = 1000000 if engine == 'splendorust' else 100000
            pilot = execute(args.threads, pilot_count)
            elapsed = pilot.get('seconds', pilot.get('elapsed_seconds'))
            count = max(pilot_count, math.ceil(pilot_count * args.target_seconds / elapsed * 1.15))
            for threads in (1, args.threads):
                configurations.append({'engine': engine, 'workload': 'opening_clone_take', 'players': 2, 'threads': threads,
                    'parallelism': 'persistent Rayon pool' if engine == 'splendorust' else 'std::thread; warmed creation excluded, release/join included',
                    'count': count, 'comparable':True, 'comparison_group': 'checked-opening-copy-take', 'unit': 'cloned validated take transitions',
                    'seed_schedule': 'opening fixture native setup seed 42' if engine == 'splendorust' else 'opening fixture native srand seed 12345; native mt19937 setup', 'pilot': pilot, 'samples': [], 'rank_scope': 'native checked opening API; single-thread primary; different pool completion costs disclosed'})
                execute(threads, min(count, pilot_count))
        rows.extend(configurations)
        save()
        for rep in range(args.repetitions):
            for row in (configurations if rep % 2 == 0 else list(reversed(configurations))):
                print(f"checked opening {row['engine']} rep{rep+1} t{row['threads']}", flush=True)
                if row['engine'] == 'splendorust':
                    sample = common_workers[row['threads']].run({'workload': 'opening_clone_take', 'players': 2, 'count': row['count']})
                else:
                    sample = json.loads(command([str(cpp), '--threads', str(row['threads']), '--seed', '12345', '--iterations', str(row['count'])]))
                assert sample['checksum'] == row['count'] and sample.get('verified', False)
                row['samples'].append(sample)
                save()
        for row in configurations:
            summary(row)
        report['common_worker_startup'] = {str(t): w.startup_seconds for t, w in common_workers.items()}
        save()
    finally:
        for worker in common_workers.values():
            worker.close()
    if not args.skip_python:
        py = ROOT / 'local/benchmarks/external/python_lyquentxy/.venv/bin/python'
        if not py.exists():
            report['failures'].append({'engine':'lyquentxy', 'status':'unsupported_setup', 'reason':'isolated Python environment is absent; run setup.py --python'})
            save()
        if py.exists():
            for mode, threads in [('compiled', 1), ('compiled', args.threads), ('public-api', 1)]:
                print(f'Python {mode} t{threads}', flush=True)
                cmd = [str(py), 'benchmarks/adapters/python_lyquentxy.py', '--root', 'local/benchmarks/external/python_lyquentxy', '--seed', '12345', '--mode', mode, '--threads', str(threads)]
                result = json.loads(command(cmd + ['--iterations', '100000', '--repetitions', str(args.repetitions), '--target-seconds', str(args.target_seconds)]))
                row = {'engine': 'lyquentxy', 'workload': 'opening_clone_take', 'mode': mode, 'players': 2, 'threads': threads,
                       'parallelism': 'Numba nogil threads' if mode == 'compiled' else 'single Python API caller', 'count': result['iterations'], 'comparison_group': 'unchecked-opening-reference',
                       'comparable':False, 'non_comparable_reason':'Timed native apply is unchecked; retained as a separate reference',
                       'unit': 'cloned prevalidated take transitions', 'samples': result['repetitions'], 'adapter_report': result}
                rows.append(summary(row))
                save()
    report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['machine']['load_at_finish'] = os.getloadavg()
    setup_metadata = ROOT / 'local/benchmarks/setup-metadata.json'
    report['setup_build'] = json.loads(setup_metadata.read_text()) if setup_metadata.exists() else {'unavailable':True}
    report['external_manifests'] = {p.name: json.loads(p.read_text()) for p in (ROOT / 'benchmarks/external').glob('*.json')}
    save()
    print(args.output, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import traceback
        failure_path = ROOT / 'local/benchmarks/last_failure.json'
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(json.dumps({'error': str(error), 'type': type(error).__name__, 'traceback': traceback.format_exc(), 'argv': __import__('sys').argv}, indent=2) + '\n')
        raise
