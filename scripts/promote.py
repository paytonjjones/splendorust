#!/usr/bin/env python3
"""Fixed-sample promotion gate. Writes evidence; never edits or reverts source files."""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(command):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def decision(report, players, margin, minimum_rate):
    if report['incomplete_games']:
        return 'reject: incomplete games'
    if not report['reproducible']:
        return 'reject: nondeterministic search budget'
    if report['games_per_second'] < minimum_rate:
        return 'reject: throughput floor'
    if report['agents'][0]['ci95'][0] > 1 / players + margin:
        return 'promote'
    return 'retain baseline: benefit not confirmed'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', default='strong')
    p.add_argument('--baseline', default='greedy')
    p.add_argument('--players', type=int, choices=[2, 3, 4], default=2)
    p.add_argument('--screen', type=int, default=2000)
    p.add_argument('--confirm', type=int, default=20000)
    p.add_argument('--seed', type=int, default=12345)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--iterations', type=int, default=128)
    p.add_argument('--margin', type=float, default=0.01)
    p.add_argument('--min-games-per-second', type=float, default=0)
    p.add_argument('--output', type=pathlib.Path, default=ROOT / 'results' / 'promotion')
    args = p.parse_args()
    if args.screen < args.players or args.confirm < args.players or args.screen % args.players or args.confirm % args.players:
        p.error('screen and confirm must be positive complete seat-rotation blocks')
    if not 0 <= args.seed < 2**64 - 1_000_000_000 - args.confirm or args.screen // args.players >= 1_000_000_000:
        p.error('seed ranges must not wrap or overlap')
    if not 0 <= args.margin < 1 or args.threads < 1 or args.min_games_per_second < 0:
        p.error('invalid margin, threads, or speed floor')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    run(['cargo', 'fmt', '--all', '--check'])
    run(['cargo', 'clippy', '--workspace', '--all-targets', '--', '-D', 'warnings'])
    run(['cargo', 'test', '--workspace', '--release', '--locked'])
    run(['cargo', 'build', '--release', '--locked'])
    binary = ROOT / 'target/release/splendor'
    run([binary, 'benchmark', '--games', 200, '--threads', args.threads])
    for stage, games, seed in [('screen', args.screen, args.seed),
                               ('confirm', args.confirm, args.seed + 1_000_000_000)]:
        output = args.output / f'{stage}.json'
        output.unlink(missing_ok=True)
        cmd = [binary, 'compare', '--agent-a', args.candidate, '--agent-b', args.baseline,
               '--games', games, '--players', args.players, '--seed', seed,
               '--threads', args.threads, '--iterations', args.iterations, '--output', output]
        proc = subprocess.run(list(map(str, cmd)), cwd=ROOT)
        if not output.exists():
            raise RuntimeError(f'{stage} failed without a report (exit {proc.returncode})')
        report = json.loads(output.read_text())
        result = decision(report, args.players, args.margin, args.min_games_per_second)
        if proc.returncode and not report['incomplete_games']:
            raise RuntimeError(f'{stage} failed: exit {proc.returncode}')
        if stage == 'screen' and not result.startswith('reject'):
            if report['agents'][0]['ci95'][1] < 1 / args.players:
                result = 'reject: screening shows regression'
            else:
                continue
        (args.output / 'decision.json').write_text(json.dumps({
            'decision': result, 'stage': stage, 'report': str(output),
            'source_id': report['source_id'], 'margin': args.margin,
            'minimum_games_per_second': args.min_games_per_second,
        }, indent=2) + '\n')
        print(result)
        return 0 if result == 'promote' else 2
    return 2


if __name__ == '__main__':
    sys.exit(main())
