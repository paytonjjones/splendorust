#!/usr/bin/env python3
"""Matched setup-block contrasts with missing-outcome bounds and hashes."""
import argparse
import collections
import gzip
import json
import math
from pathlib import Path
from boundary import ARMS, sha, stream
import numpy as np

SETTINGS = ['ruleset', 'master', 'games', 'iterations', 'depth', 'world_pool', 'root_only', 'search',
            'cpuct', 'fpu_reduction', 'uniform_prior', 'external_config', 'upstream_revision',
            'upstream_checkpoint_sha256', 'model_sha256', 'source_id', 'source_sha256']

def load(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as f:
        meta = json.loads(next(f))
        rows = [json.loads(line) for line in f]
    return meta, rows

def summarize(stage, replicates=20000):
    data = {}
    for arm in ARMS:
        path = stage/arm/'games.jsonl'
        if not path.exists(): path = path.with_suffix('.jsonl.gz')
        meta, rows = load(path)
        assert meta['information_arm'] == arm and len(rows) == meta['games']
        assert len(rows) % 2 == 0
        data[arm] = (meta, rows, path)
    control_meta, control_rows, _ = data['control']
    blocks = len(control_rows)//2
    lower, upper = [], []
    arms = {}
    for arm, (meta, rows, path) in data.items():
        assert all(meta[k] == control_meta[k] for k in SETTINGS), 'different frozen settings'
        lo, hi = [], []
        for i, row in enumerate(rows):
            control = control_rows[i]
            assert row['index'] == i and row['block'] == i//2 and row['rotation'] == i%2
            for key in ['initial_state', 'setup_seed', 'policy_seeds', 'seats']:
                assert row[key] == control[key], ('unpaired game', arm, i, key)
            assert row['policy_seeds'] == [stream(meta['master'], 'policy', row['block'], x) for x in range(2)]
            assert row['setup_seed'] == stream(meta['master'], 'setup', row['block'])
            if i%2: assert row['initial_state'] == rows[i-1]['initial_state']
            credit = row['rewards'][row['seats'].index('champion')] if row['status'] == 'complete' else None
            lo.append(0 if credit is None else credit)
            hi.append(1 if credit is None else credit)
        lo = np.asarray(lo).reshape(-1, 2).mean(axis=1)
        hi = np.asarray(hi).reshape(-1, 2).mean(axis=1)
        lower.append(lo); upper.append(hi)
        radius = math.sqrt(math.log(2/.05)/(2*blocks))
        arms[arm] = dict(games=len(rows), statuses=dict(collections.Counter(r['status'] for r in rows)),
            credit_bounds=[float(lo.mean()), float(hi.mean())],
            hoeffding95=[max(0., float(lo.mean())-radius), min(1.,float(hi.mean())+radius)],
            seat_credit_bounds={str(seat): [sum((r['rewards'][seat] if r['status']=='complete' else endpoint) for r in rows if r['seats'][seat]=='champion')/blocks for endpoint in [0,1]] for seat in range(2)},
            terminal_categories=dict(collections.Counter(r.get('termination', 'incomplete') for r in rows)),
            cap_unknown_credit_bounds=[sum(r['rewards'][r['seats'].index('champion')] if r['status']=='complete' and r.get('termination')!='native_turn_cap' else endpoint for r in rows)/len(rows) for endpoint in [0,1]],
            simulations=sum(r['simulations'] for r in rows), inferences=sum(r['inferences'] for r in rows),
            policy_seconds={identity:sum(r['policy_seconds'][r['seats'].index(identity)] for r in rows) for identity in ['champion','alphazero']},
            wall_seconds=meta['wall_seconds'], raw_file=str(path.relative_to(stage)), raw_sha256=sha(path))
    lower, upper = np.array(lower), np.array(upper)
    # Same independent blocks in every arm, including both seat rotations.
    rng = np.random.default_rng(491991)
    boot_lo, boot_hi = [], []
    for _ in range(replicates):
        selected = rng.integers(blocks, size=blocks)
        boot_lo.append(lower[:, selected].mean(axis=1))
        boot_hi.append(upper[:, selected].mean(axis=1))
    boot_lo, boot_hi = np.array(boot_lo), np.array(boot_hi)
    def interval(lo, hi, alpha=.05):
        return [float(np.quantile(lo, alpha/2)), float(np.quantile(hi, 1-alpha/2))]
    contrasts = {}
    for index, arm in enumerate(ARMS):
        arms[arm]['paired_bootstrap95_missing_envelope'] = interval(boot_lo[:,index], boot_hi[:,index])
        if index == 0: continue
        dlo, dhi = lower[index]-upper[0], upper[index]-lower[0]
        # Two contrasts; four one-sided tails. Differences are in [-1,1].
        radius = math.sqrt(2*math.log(4/.05)/blocks)
        denominator_lo, denominator_hi = .5-upper[0].mean(), .5-lower[0].mean()
        fraction = None; fraction_ci = None
        if denominator_lo > 0:
            values = [dlo.mean()/denominator_lo, dlo.mean()/denominator_hi,
                      dhi.mean()/denominator_lo, dhi.mean()/denominator_hi]
            fraction = [float(min(values)), float(max(values))]
            if np.all(.5-boot_hi[:,0] > 0):
                differences = [boot_lo[:,index]-boot_hi[:,0], boot_hi[:,index]-boot_lo[:,0]]
                denominators = [.5-boot_hi[:,0], .5-boot_lo[:,0]]
                ratios = [d/g for d in differences for g in denominators]
                frac_lo = np.minimum.reduce(ratios)
                frac_hi = np.maximum.reduce(ratios)
                fraction_ci = interval(frac_lo, frac_hi)
        contrasts[arm] = dict(delta_credit_bounds=[float(dlo.mean()), float(dhi.mean())],
            paired_bootstrap95=interval(boot_lo[:,index]-boot_hi[:,0], boot_hi[:,index]-boot_lo[:,0]),
            paired_bootstrap97_5=interval(boot_lo[:,index]-boot_hi[:,0], boot_hi[:,index]-boot_lo[:,0], .025),
            simultaneous_hoeffding95=[max(-1., float(dlo.mean())-radius), min(1.,float(dhi.mean())+radius)],
            control_gap_reduced_fraction_bounds=fraction, control_gap_reduced_fraction_bootstrap95=fraction_ci)
    return dict(schema='information-fair-native-v1', blocks=blocks, settings={k:control_meta[k] for k in SETTINGS},
                arms=arms, contrasts=contrasts, script_sha256=sha(__file__), bootstrap_replicates=replicates,
                bootstrap_seed=491991, scope='Independent information interventions at frozen rules/model/search budgets. Setup blocks are the sampling unit; incomplete outcomes retain [0,1] credit. Gap fractions are not additive. No canonical or equal-compute claim.')

def main():
    p=argparse.ArgumentParser(); p.add_argument('stage',type=Path); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=summarize(a.stage)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'arms':{k:v['credit_bounds'] for k,v in result['arms'].items()}, 'contrasts':result['contrasts']},indent=2))

if __name__=='__main__': main()
