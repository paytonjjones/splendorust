#!/usr/bin/env python3
"""Create the final report and verify all evidence after the frozen protocol."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PYTHON = ROOT / 'local/strength/inference/bin/python'


def interval(values):
    return '–'.join(f'{100 * v:.2f}%' for v in values)


def main():
    status = json.loads((BASE / 'protocol-status.json').read_text())
    assert status['status'] == 'complete', 'protocol is not complete'
    subprocess.run([str(PYTHON), str(BASE / 'review_cap.py'), '--output',
                    str(BASE / 'cap-review.json')], check=True, cwd=ROOT)
    stages = ['screen', 'confirmation', 'higher-search']
    results = {name: json.loads((BASE / name / 'summary.json').read_text())
               for name in stages}
    for name, result in results.items():
        assert result['statuses'] == {'complete': result['games']}, name
        assert result['completion_rate'] == 1 and result['pairing_verified'], name
    primary = results['confirmation']
    higher = results['higher-search']
    rows = []
    for name, label in [('screen', 'Screen'), ('confirmation', 'Primary confirmation'),
                        ('higher-search', 'Higher-search control')]:
        s = results[name]
        rows.append(f"| {label} | {s['metadata']['iterations']} | {s['games']:,} | "
                    f"{100 * s['completion_rate']:.2f}% | {s['candidate_credit_total']:,.1f} | "
                    f"{100 * s['candidate_credit_conditional_rate']:.3f}% | "
                    f"{interval(s['conservative_hoeffding95_missing_envelope'])} | "
                    f"{interval(s['paired_bootstrap95_missing_envelope'])} |")
    section = '''## Fresh results

All three schedules completed. Every game passed replay against the unchanged
upstream referee. There were no unsupported, invalid, blocked or incomplete
games. AlphaZero used its unchanged 800-simulation setting in every schedule.
Win credit gives one credit to a sole winner and half to each shared winner.

| Schedule | SR iterations | Games | Completion | SR credits | SR win credit | Conservative 95% interval | Paired bootstrap 95% interval |
|---|---:|---:|---:|---:|---:|---|---|
''' + '\n'.join(rows) + '\n\n'
    section += (f"The primary endpoint is the fresh {primary['games']:,}-game confirmation, "
                f"with {primary['setup_blocks']:,}\nindependent setup blocks and both seat rotations. "
                "The conservative interval uses\nHoeffding's bound on block credits in [0,1]. "
                "The bootstrap resamples whole setup\nblocks. These intervals assume independent "
                "blocks under the declared RNG streams.\nThe screen and higher-search control "
                "are separate endpoints; they are not pooled.\n\n")
    if primary['conservative_hoeffding95_missing_envelope'][1] < .5:
        section += ('Unchanged AlphaZero is stronger than frozen E56 at the primary settings in\n'
                    'this native profile. The conservative upper bound for E56 is below 50%.\n')
    elif primary['conservative_hoeffding95_missing_envelope'][0] > .5:
        section += ('Frozen E56 is stronger at the primary settings in this native profile.\n'
                    'Its conservative lower bound is above 50%.\n')
    else:
        section += ('The conservative primary interval crosses 50%. It does not establish\n'
                    'which agent is stronger at these settings.\n')
    section += ('The information difference prevents an equal-information claim. The result\n'
                'does not rank the agents under canonical published Splendor.\n\n')
    section += (f"The pre-registered higher-search control used the same E56 weights and\n"
                f"800 iterations. Its win credit was {100 * higher['candidate_credit_conditional_rate']:.3f}%. "
                "It is an exploratory\ncompute control, with fresh seeds and a smaller schedule. "
                "It is not a training\ngain, a paired comparison with the primary schedule, "
                "or an equal-compute claim.\n\n")
    section += '| Schedule | SR seat 0 credit | SR seat 1 credit | Terminal categories | Replayed moves |\n|---|---:|---:|---|---:|\n'
    for name in stages:
        s = results[name]
        replay = json.loads((BASE / name / 'replay.json').read_text())
        credit = [100 * s['per_seat'][str(i)]['credit'] / s['per_seat'][str(i)]['games']
                  for i in range(2)]
        categories = ', '.join(f'{k}: {v:,}' for k, v in s['terminal_categories'].items())
        section += f"| {name} | {credit[0]:.3f}% | {credit[1]:.3f}% | {categories} | {replay['checked_transitions']:,} |\n"
    section += ('\n`native_score` means the 15-point condition. `native_turn_cap` means the\n'
                'upstream 124-turn condition. Both use the upstream score and purchased-card\n'
                'tie break. No cap is assigned a fabricated canonical outcome.\n\n')
    section += ('The sole cap case was confirmation game 3188, block 1594, rotation 0.\n'
                'At turn 124, E56 had 1 point and AlphaZero had 12. E56 passed 47 times;\n'
                'AlphaZero passed 35 times. The unchanged native referee awarded AlphaZero\n'
                'the win. The last legal sets and an extra state/reward check are saved in\n'
                '`cap-review.json`. Treating this one result as unknown gives primary\n'
                'credit bounds of 23.395%–23.400%; the conservative upper bound remains\n'
                'below 50%. This sensitivity check does not replace the native protocol.\n\n')
    section += '## Recorded runtime\n\n| Schedule | Eight-worker wall seconds | Games/second | SR policy seconds, sum | AlphaZero policy seconds, sum | SR simulations | SR inferences |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for name in stages:
        s = results[name]
        section += (f"| {name} | {s['wall_seconds']:,.2f} | {s['games'] / s['wall_seconds']:.3f} | "
                    f"{s['policy_seconds']['champion']:,.2f} | {s['policy_seconds']['alphazero']:,.2f} | "
                    f"{s['simulations']:,} | {s['inferences']:,} |\n")
    section += ('\nPolicy seconds are measured elapsed time per decision, summed over concurrent\n'
                'games. They are not isolated CPU seconds. Schedule wall time includes worker\n'
                'startup but excludes the later replay, compression and summary steps. Search\n'
                'budgets are fixed; runtime is reported rather than used to assert equal compute.\n\n')
    report_path = BASE / 'REPORT.md'
    report = report_path.read_text()
    report = report.replace('Status: the frozen 20,000-game confirmation and 2,000-game higher-search control\nare running. This file will contain the final results after both schedules pass\nreplay. The 2,000-game screen is complete.',
                            'Status: complete. The fresh 20,000-game confirmation and both 2,000-game\ncontrols completed and passed native replay.')
    start = report.index('## Completed screen' if '## Completed screen' in report
                         else '## Fresh results')
    end = report.index('## Runtime control')
    report = report[:start] + section + report[end:]
    report = report.replace('will record compressed and exact raw hashes',
                            'records compressed and exact raw hashes')
    audit_section = '''

The final audit command checks the frozen files, all lossless archives and each
completed schedule's replay evidence:

```sh
local/strength/inference/bin/python benchmarks/strength/native/audit_results.py \\
  --runtime --output benchmarks/strength/native/final-audit.json
```

`artifact-manifest.json` contains the exact hashes of the final documentation,
commands, validation logs, summaries, replay evidence and compressed records.
The compiled source stays pinned to the frozen code revision above; the later
results commit does not change that binary or the benchmark settings.
'''
    if 'The final audit command checks' not in report:
        report += audit_section
    report_path.write_text(report)
    subprocess.run([str(PYTHON), str(BASE / 'archive.py')], check=True, cwd=ROOT)
    with (BASE / 'final-audit.log').open('w') as log:
        subprocess.run([str(PYTHON), str(BASE / 'audit_results.py'), '--runtime',
                        '--output', str(BASE / 'final-audit.json')],
                       check=True, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    # The manifest excludes itself and raw copies; archive-index holds raw hashes.
    files = {}
    for path in sorted(BASE.rglob('*')):
        if (not path.is_file() or '__pycache__' in path.parts
                or path.suffix == '.jsonl' or path.name == 'artifact-manifest.json'):
            continue
        files[str(path.relative_to(BASE))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (BASE / 'artifact-manifest.json').write_text(json.dumps(dict(
        code_revision=primary['metadata']['revision'],
        profile=primary['metadata']['ruleset'],
        raw_hash_index='archive-index.json', file_sha256=files), indent=2) + '\n')
    print('Final report, archives, audit and artifact manifest complete', flush=True)


if __name__ == '__main__':
    main()
