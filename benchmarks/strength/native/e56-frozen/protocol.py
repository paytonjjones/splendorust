#!/usr/bin/env python3
"""Execute the pre-registered frozen native benchmark through all stages."""
import json
import subprocess
import time
from pathlib import Path
from schedule import PYTHON,run_schedule
from upstream import ROOT,sha

def main():
    base=Path(__file__).resolve().parent
    freeze=json.loads((base/'frozen-manifest.json').read_text())
    stages=[('screen',2000,4110000000,128),('confirmation',20000,4120000000,128),('higher-search',2000,4150000000,800)]
    for name,games,master,iterations in stages:
        for path,digest in freeze['source_model_binary_sha256'].items():assert sha(ROOT/path)==digest,('frozen source/model/binary changed',path)
        for path,digest in freeze['harness_sha256'].items():assert sha(ROOT/path)==digest,('frozen harness changed',path)
        progress=dict(stage=name,status='running',games=games,master=master,iterations=iterations,workers=8)
        (base/'protocol-status.json').write_text(json.dumps(progress,indent=2)+'\n')
        print('START',name,games,master,iterations,flush=True)
        execution=run_schedule(base/name,games,master,8,iterations)
        for script,output in [('replay.py','replay.json'),('summarize.py','summary.json')]:
            command=[str(PYTHON),str(base/script),str(base/name/'games.jsonl'),'--output',str(base/name/output)]
            with (base/name/(script+'.log')).open('w') as log:
                subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
        progress.update(status='complete',wall_seconds=execution['wall_seconds'])
        (base/'protocol-status.json').write_text(json.dumps(progress,indent=2)+'\n')
        print('COMPLETE',name,execution['wall_seconds'],flush=True)
    (base/'protocol-status.json').write_text(json.dumps(dict(status='complete',stages=[name for name,*_ in stages]),indent=2)+'\n')
if __name__=='__main__':main()
