#!/usr/bin/env python3
"""Independent setup-block uncertainty, preserving all unknown outcomes."""
import argparse
import collections
import hashlib
import json
import math
import statistics
from pathlib import Path
from upstream import sha
import importlib.util
spec=importlib.util.spec_from_file_location('diagnostic_summary',Path(__file__).resolve().parents[1]/'summarize.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=module.summarize(a.input)
    meta,*rows=map(json.loads,a.input.read_text().splitlines())
    lower=[b['lower'] for b in result['block_credits']];upper=[b['upper'] for b in result['block_credits']]
    # Distribution-free Hoeffding interval for independent setup blocks in [0,1].
    # Union-bound the lower and upper missing-credit means (two one-sided tails).
    radius=math.sqrt(math.log(2/.05)/(2*len(lower)))
    actions=collections.Counter();by_identity={x:collections.Counter() for x in ['champion','alphazero']}
    for row in rows:
        actions.update(row['actions'])
        for turn,action in enumerate(row['actions']):by_identity[row['seats'][turn%2]][action]+=1
    result.update(completion_rate=result['statuses'].get('complete',0)/len(rows),
        conservative_hoeffding95_missing_envelope=[max(0,statistics.mean(lower)-radius),min(1,statistics.mean(upper)+radius)],
        terminal_categories=dict(collections.Counter(r.get('termination','unknown') for r in rows)),
        elapsed_game_seconds=sum(r['elapsed_seconds'] for r in rows),wall_seconds=meta.get('wall_seconds'),
        policy_seconds={identity:sum(r['policy_seconds'][r['seats'].index(identity)] for r in rows) for identity in ['champion','alphazero']},
        simulations=sum(r['simulations'] for r in rows),inferences=sum(r['inferences'] for r in rows),
        actions_by_identity={i:dict(sorted(c.items())) for i,c in by_identity.items()},
        source_sha256=sha(__file__),
        conclusion_scope='Frozen models and fixed search budgets in AlphaZero native rules. Unchanged AlphaZero has true private reservation/deck-membership information; SplendoRust uses public observations. Native cap outcomes are legitimate native results. No canonical or equal-compute rank.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['games','statuses','candidate_credit_conditional_rate','paired_bootstrap95_missing_envelope','conservative_hoeffding95_missing_envelope']}))
if __name__=='__main__':main()
