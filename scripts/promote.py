#!/usr/bin/env python3
"""Fixed-sample promotion gate. Writes evidence; never edits or reverts source files."""
import argparse
import hashlib
import json
import math
import pathlib
import subprocess
import sys

from collect_evidence import record_interval, validate_report

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURRENT_ENGINE = 'splendorust-v2'
COMPLETION_POLICY_VERSION = 'bounded-no-action-v2.1'
DEFAULT_MAX_NO_ACTION_FRACTION = 0.01


def completion_policy(max_no_action_fraction=DEFAULT_MAX_NO_ACTION_FRACTION):
    if (type(max_no_action_fraction) not in (int, float)
            or not math.isfinite(max_no_action_fraction)
            or not 0 <= max_no_action_fraction <= 1):
        raise ValueError('invalid maximum no-action fraction')
    return dict(version=COMPLETION_POLICY_VERSION,
                max_no_action_fraction=max_no_action_fraction,
                tolerated_status='no_legal_action', decision_limit='reject',
                lower_unknown_credit=0, upper_unknown_credit=1,
                denominator='all requested games', replace_or_skip=False)


def completion_rejection(report, max_no_action_fraction=DEFAULT_MAX_NO_ACTION_FRACTION):
    """Apply the registered completion guard after report validation."""
    completion_policy(max_no_action_fraction)
    if any(r['status'] == 'decision_limit' for r in report['records']):
        return 'reject: decision-limit games'
    count = sum(r['status'] == 'no_legal_action' for r in report['records'])
    if count > math.floor(report['requested_games'] * max_no_action_fraction):
        return 'reject: no-action fraction exceeds policy'
    return None


def completion_evidence(report, max_no_action_fraction=DEFAULT_MAX_NO_ACTION_FRACTION):
    """Preserve unknown outcomes; report credit bounds over all requested games."""
    validate_report(report)
    counts = {status: sum(r['status'] == status for r in report['records'])
              for status in ('complete', 'no_legal_action', 'decision_limit')}
    known_credit = sum(1 / r['winners'].bit_count() for r in report['records']
                       if r['status'] == 'complete'
                       and r['winners'] & (1 << r['seats'].index(0)))
    return dict(policy=completion_policy(max_no_action_fraction), status_counts=counts,
                max_no_action_games=math.floor(report['requested_games'] * max_no_action_fraction),
                requested_games=report['requested_games'],
                candidate_credit_bounds=[known_credit / report['requested_games'],
                                        (known_credit + report['incomplete_games']) / report['requested_games']],
                rejection=completion_rejection(report, max_no_action_fraction))


def supported_source(report):
    return (report.get('engine') == CURRENT_ENGINE
            and isinstance(report.get('source_id'), str) and bool(report['source_id']))


def run(command):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def build_release(output):
    """Use Cargo's actual executable, including custom target dirs and targets."""
    command = ['cargo', 'build', '--release', '--locked', '--package', 'splendor-arena',
               '--bin', 'splendor', '--message-format=json']
    print('+', ' '.join(command), flush=True)
    proc = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, text=True)
    (output / 'cargo-build.jsonl').write_text(proc.stdout)
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, command)
    executables = set()
    for line in proc.stdout.splitlines():
        message = json.loads(line)
        target = message.get('target', {})
        if (message.get('reason') == 'compiler-artifact'
                and target.get('name') == 'splendor' and target.get('kind') == ['bin']
                and message.get('profile', {}).get('test') is False
                and message.get('executable')):
            executables.add(pathlib.Path(message['executable']).resolve())
    if len(executables) != 1:
        raise RuntimeError('Cargo did not report exactly one splendor executable')
    binary = executables.pop()
    (output / 'build.json').write_text(json.dumps({
        'command': command, 'executable': str(binary),
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    return binary


def checked_interval(report, players):
    """Reject malformed evidence and derive the candidate interval from records."""
    validate_report(report)
    if report['players'] != players or [a['identity'] for a in report['agents']] != list(range(players)):
        raise ValueError('report identities do not match the requested comparison')
    computed = record_interval(report['records'], players, 0)
    supplied = report['agents'][0]['ci95']
    if (len(supplied) != 2 or not all(type(x) in (int, float) and math.isfinite(x) for x in supplied)
            or not 0 <= supplied[0] <= supplied[1] <= 1
            or not all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                       for a, b in zip(supplied, computed))):
        raise ValueError('candidate interval disagrees with game records')
    rate, elapsed = report['games_per_second'], report['runtime_seconds']
    if (type(rate) not in (int, float) or type(elapsed) not in (int, float)
            or not math.isfinite(rate) or not math.isfinite(elapsed) or rate <= 0 or elapsed <= 0
            or not math.isclose(rate, report['requested_games'] / elapsed, rel_tol=1e-9)):
        raise ValueError('throughput disagrees with elapsed time and game count')
    return computed


def decision(report, players, margin, minimum_rate,
             max_no_action_fraction=DEFAULT_MAX_NO_ACTION_FRACTION):
    if not supported_source(report):
        return 'reject: unsupported engine or missing source identity'
    try:
        lower, _ = checked_interval(report, players)
        completion_error = completion_rejection(report, max_no_action_fraction)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as error:
        return f'reject: invalid report evidence: {error}'
    if completion_error:
        return completion_error
    if report['reproducible'] is not True:
        return 'reject: nondeterministic search budget'
    if report['games_per_second'] < minimum_rate:
        return 'reject: throughput floor'
    if lower > 1 / players + margin:
        return 'promote'
    return 'retain baseline: benefit not confirmed'


def setup_seed(master, block):
    """Version-1 arena SplitMix64 schedule, checked against recorded setups."""
    mask = 2**64 - 1
    value = (master + block + 0x9e3779b97f4a7c15) & mask
    value = ((value ^ (value >> 30)) * 0xbf58476d1ce4e5b9) & mask
    value = ((value ^ (value >> 27)) * 0x94d049bb133111eb) & mask
    return value ^ (value >> 31)


def validate_stage(report, args, games, seed, previous_source):
    validate_report(report)
    expected = {
        'names': [args.candidate] + [args.baseline] * (args.players - 1),
        'games': games, 'seed': seed, 'threads': args.threads,
        'max_decisions': 20000, 'check': False,
        'search': {'iterations': args.iterations, 'depth': getattr(args, 'depth', 8), 'width': 6,
                   'time_budget': None, 'rollout': 'strong', 'evaluation': 'engine'},
    }
    if report.get('run_config') != expected:
        raise ValueError('report settings differ from the requested stage')
    source = (report['engine'], report['source_id'])
    if (not supported_source(report)
            or (previous_source is not None and source != previous_source)):
        raise ValueError('unsupported engine or source changed between stages')
    for record in report['records']:
        if record['seed'] != setup_seed(seed, record['block']):
            raise ValueError('record setup seed differs from the requested schedule')
    return source


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', default='strong')
    p.add_argument('--baseline', default='greedy')
    p.add_argument('--players', type=int, choices=[2, 3, 4], default=2)
    p.add_argument('--screen', type=int, default=2000)
    p.add_argument('--confirm', type=int, default=0, help='0: fixed screen-only inner-loop gate; use 20000 for milestone confirmation')
    p.add_argument('--seed', type=int, default=12345)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--iterations', type=int, default=128)
    p.add_argument('--depth', type=int, default=8)
    p.add_argument('--margin', type=float, default=0.01)
    p.add_argument('--min-games-per-second', type=float, default=0)
    p.add_argument('--max-no-action-fraction', type=float, default=DEFAULT_MAX_NO_ACTION_FRACTION,
                   help='maximum no-legal-action fraction per stage; 0 restores strict completion')
    p.add_argument('--output', type=pathlib.Path, default=ROOT / 'results' / 'promotion')
    args = p.parse_args(argv)
    if args.screen < args.players or (args.confirm != 0 and args.confirm < args.players) or args.screen % args.players or args.confirm % args.players:
        p.error('screen must be positive; confirm may be zero; counts must use complete seat-rotation blocks')
    if not 0 <= args.seed < 2**64 - 1_000_000_000 - args.confirm or args.screen // args.players >= 1_000_000_000:
        p.error('seed ranges must not wrap or overlap')
    if not 0 <= args.margin < 1 or args.threads < 1 or not math.isfinite(args.min_games_per_second) or args.min_games_per_second < 0:
        p.error('invalid margin, threads, or speed floor')
    if not 0 <= args.iterations < 2**32 or not 0 <= args.depth < 2**32:
        p.error('iterations and depth must fit unsigned 32-bit counts')
    try:
        args.completion_policy = completion_policy(args.max_no_action_fraction)
    except ValueError as error:
        p.error(str(error))
    args.output = args.output.resolve()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        p.error('output already exists; choose a new directory to preserve prior evidence')
    args.evidence_tools_sha256 = {
        name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
        for name in ('promote.py', 'collect_evidence.py')
    }
    manifest = vars(args).copy()
    manifest['output'] = str(args.output)
    manifest['confirmation_seed'] = args.seed + 1_000_000_000
    (args.output / 'run.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        return execute(args)
    except (subprocess.CalledProcessError, RuntimeError, OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
        (args.output / 'decision.json').write_text(json.dumps({
            'decision': 'reject: execution failure', 'error': str(error),
        }, indent=2) + '\n')
        print(f'reject: execution failure: {error}', file=sys.stderr)
        return 2


def execute(args):
    run(['cargo', 'fmt', '--all', '--check'])
    run(['cargo', 'clippy', '--workspace', '--all-targets', '--locked', '--', '-D', 'warnings'])
    run(['cargo', 'test', '--workspace', '--release', '--locked'])
    binary = build_release(args.output)
    run([binary, 'benchmark', '--games', 200, '--threads', args.threads])
    previous_source = None
    stages = [('screen', args.screen, args.seed)]
    if args.confirm:
        stages.append(('confirm', args.confirm, args.seed + 1_000_000_000))
    for stage, games, seed in stages:
        output = args.output / f'{stage}.json'
        cmd = [binary, 'compare', '--agent-a', args.candidate, '--agent-b', args.baseline,
               '--games', games, '--players', args.players, '--seed', seed,
               '--threads', args.threads, '--iterations', args.iterations,
               '--depth', args.depth, '--width', 6, '--rollout', 'strong', '--evaluation', 'engine',
               '--max-decisions', 20000, '--output', output]
        proc = subprocess.run(list(map(str, cmd)), cwd=ROOT)
        if not output.exists():
            raise RuntimeError(f'{stage} failed without a report (exit {proc.returncode})')
        raw = output.read_bytes()
        report = json.loads(raw)
        previous_source = validate_stage(report, args, games, seed, previous_source)
        result = decision(report, args.players, args.margin, args.min_games_per_second,
                          args.max_no_action_fraction)
        if proc.returncode not in (0, 1) or (proc.returncode == 1 and not report['incomplete_games']):
            raise RuntimeError(f'{stage} failed: exit {proc.returncode}')
        (args.output / f'{stage}-completion.json').write_text(json.dumps(
            completion_evidence(report, args.max_no_action_fraction), indent=2) + '\n')
        if stage == 'screen' and args.confirm and not result.startswith('reject'):
            if record_interval(report['records'], args.players, 0)[1] < 1 / args.players:
                result = 'reject: screening shows regression'
            else:
                continue
        (args.output / 'decision.json').write_text(json.dumps({
            'decision': result, 'stage': stage, 'report': str(output),
            'source_id': report['source_id'], 'margin': args.margin,
            'interval_from_records': record_interval(report['records'], args.players, 0),
            'evidence_tools_sha256': args.evidence_tools_sha256,
            'raw_report_sha256': hashlib.sha256(raw).hexdigest(),
            'record_set_sha256': hashlib.sha256(json.dumps(report['records'], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'minimum_games_per_second': args.min_games_per_second,
            'completion': completion_evidence(report, args.max_no_action_fraction),
        }, indent=2) + '\n')
        print(result)
        return 0 if result == 'promote' else 2
    return 2


if __name__ == '__main__':
    sys.exit(main())
