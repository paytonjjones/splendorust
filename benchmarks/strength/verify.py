#!/usr/bin/env python3
"""Replay every canonical history and check terminal credit and final scores."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    process=subprocess.Popen([ROOT/'target/release/examples/strength_replay'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    checked={}
    try:
        for path in sorted((ROOT/'benchmarks/strength/results').glob('*.jsonl')):
            meta,*rows=map(json.loads,path.read_text().splitlines())
            if meta.get('engine')=='seal256_native' or path.name.startswith('rejected-'):continue
            if len(rows)!=meta['games']:raise ValueError('missing records: '+str(path))
            for row in rows:
                process.stdin.write(json.dumps({'players':meta['players'],'seed':row['setup_seed'],'actions':row['actions']})+'\n');process.stdin.flush()
                result=json.loads(process.stdout.readline())
                assert result['scores']==row['scores'],(path,row['index'],'scores')
                assert result['turns']==row['turns'],(path,row['index'],'turns')
                if row['status']=='complete':
                    winners=result['winners'];assert winners is not None
                    assert row['rewards']==[1/winners.bit_count() if winners&(1<<i) else 0 for i in range(meta['players'])]
                else:assert result['winners'] is None and row['rewards'] is None
            checked[path.name]=len(rows)
    finally:
        process.stdin.close();process.wait();process.stdout.close()
    (ROOT/'benchmarks/strength/replay-validation.json').write_text(json.dumps({'checked_games':sum(checked.values()),'files':checked,
        'scope':'Every saved canonical transition passes public apply and invariants. Final scores, turns and normal terminal credits match. Does not independently prove external policy equivalence.'},indent=2)+'\n')
    print(sum(checked.values()),'games verified')
if __name__=='__main__':main()
