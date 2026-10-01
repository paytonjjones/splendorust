#!/usr/bin/env python3
"""Same fixed schedule at 1/4/8 processes; require trajectory equality."""
import json
from pathlib import Path
from schedule import run_schedule
from upstream import ROOT

def records(path):
    _,*rows=map(json.loads,path.read_text().splitlines())
    return [{k:v for k,v in r.items() if k not in ['elapsed_seconds','policy_seconds']} for r in rows]

def main():
    base=ROOT/'benchmarks/strength/native/scaling';results=[];reference=None
    for workers in [1,4,8]:
        directory=base/f'workers-{workers}'
        result=run_schedule(directory,128,4140000000,workers)
        trace=records(directory/'games.jsonl')
        if reference is None:reference=trace
        else:assert trace==reference,('concurrency affects actions',workers)
        results.append(dict(workers=workers,games=128,wall_seconds=result['wall_seconds'],games_per_second=128/result['wall_seconds'],exact_records_equal=True))
        (base/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
        print(results[-1],flush=True)
if __name__=='__main__':main()
