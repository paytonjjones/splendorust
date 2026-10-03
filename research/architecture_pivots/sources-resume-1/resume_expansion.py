"""Resume interrupted collectors; retain checked shards and partial artifacts."""
import concurrent.futures
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha

def main():
    out=ROOT/'research/architecture_pivots/expansion'
    plan=json.loads((out/'plan.json').read_text())
    # The original driver can change; frozen teacher/data dependencies cannot.
    for path,digest in plan['hashes'].items():
        if path.endswith('collect_expansion.py'):continue
        assert sha(ROOT/path)==digest,path
    local=ROOT/'local/research/architecture-pivots/expansion/train'
    stamp=str(time.time_ns());start=time.monotonic()
    archive=local.parent/f'interrupted-{stamp}'
    receipts=[];pending=[]
    for offset in range(0,plan['games'],200):
        dest=local/f'{offset:06}'
        if (dest/'checks.json').exists():
            r=json.loads((dest/'checks.json').read_text())
            assert r['games']==r['completed']==min(200,plan['games']-offset)
            for name,field in [('data.bin','data_sha256'),('data.context.bin','context_sha256'),('histories.json.gz','histories_sha256')]:
                assert sha(dest/name)==r[field]
            receipts.append(r)
        else:
            if dest.exists():
                archive.mkdir(parents=True,exist_ok=True);dest.rename(archive/dest.name)
            pending.append(offset)
    (out/f'resume-{stamp}.json').write_text(json.dumps(dict(script_sha256=sha(__file__),retained_games=sum(r['games'] for r in receipts),pending_offsets=pending,partial_archive=str(archive)),indent=2)+'\n')
    def collect(offset):
        with (out/f'{offset:06}-resume-{stamp}.log').open('w') as stream:
            subprocess.run([sys.executable,str(ROOT/'research/e95/collect.py'),'--master',str(plan['master']),'--offset',str(offset),'--games',str(min(200,plan['games']-offset)),'--output',str(local/f'{offset:06}')],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
        return json.loads((local/f'{offset:06}'/'checks.json').read_text())
    def progress():
        result=dict(completed_games=sum(r['games'] for r in receipts),rows=sum(r['rows'] for r in receipts),seconds_this_resume=time.monotonic()-start,receipts=receipts)
        (out/'progress.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='receipts'}),flush=True)
        return result
    progress()
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan['workers']) as pool:
        futures=[pool.submit(collect,i) for i in pending]
        for future in concurrent.futures.as_completed(futures):receipts.append(future.result());progress()
    result=progress();assert result['completed_games']==plan['games']
    (out/'complete.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
