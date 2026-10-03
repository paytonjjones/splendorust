"""Add fresh canonical E81 Gumbel800 data and public histories."""
import json
import os
import subprocess
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
from pools import unseen


def main():
    out=ROOT/'research/architecture_pivots/canonical-expansion';out.mkdir(exist_ok=True)
    local=ROOT/'local/research/architecture-pivots/expansion/canonical';local.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e81/model/model.bin')
    binary=out/'flywheel_data.bin'
    if not binary.exists():
        import shutil
        shutil.copy2(ROOT/'target/release/examples/flywheel_data',binary)
    binary_hash=sha(binary)
    plan=dict(games=4000,seed=5120000000,policy_seed_offset=3000000000,iterations=800,depth=16,
        threads=4,binary_sha256=binary_hash,model_sha256=sha(ROOT/'research/e81/model/model.bin'))
    if (out/'plan.json').exists():assert json.loads((out/'plan.json').read_text())==plan
    else:(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    receipts=json.loads((out/'progress.json').read_text()) if (out/'progress.json').exists() else []
    for r in receipts:
        index=r['index'];dest=local/f'{index:02d}.data.bin'
        base=ROOT/'local/research/architecture-pivots'/f'expanded-canonical-{index:02d}'
        for path,key in [(dest,'data'),(dest.with_suffix('.context.bin'),'context'),(Path(str(base)+'.history.bin'),'history'),(Path(str(base)+'.aux.bin'),'aux'),(Path(str(base)+'.pool.bin'),'pool')]:assert sha(path)==r[key+'_sha256']
    for index in range(4):
        if any(r['index']==index for r in receipts):continue
        seed=5120000000+index*1000;dest=local/f'{index:02d}.data.bin'
        cmd=[binary,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,
             '--iterations',800,'--teacher-agent','flywheel-gumbel','--teacher-action-targets',
             '--public-context','--public-history','--depth',16,'--threads',4,'--output',dest]
        with (out/f'{index:02d}.log').open('w') as log:
            subprocess.run(list(map(str,cmd)),env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        report=json.loads(dest.with_suffix('.json').read_text())
        assert report['complete']==1000 and report['blocked']==report['capped']==0
        base=ROOT/'local/research/architecture-pivots'/f'expanded-canonical-{index:02d}'
        dest.with_suffix('.history.bin').rename(str(base)+'.history.bin')
        dest.with_suffix('.aux.bin').rename(str(base)+'.aux.bin')
        rows=np.memmap(dest,mode='r',dtype=DTYPE)
        context=np.fromfile(dest.with_suffix('.context.bin'),dtype='<f4').reshape(-1,7)
        pool=np.memmap(str(base)+'.pool.bin',mode='w+',dtype='<f4',shape=(len(rows),90))
        for i in range(0,len(rows),4096):pool[i:i+4096]=unseen(rows['x'][i:i+4096],context[i:i+4096])
        pool.flush()
        receipts.append(dict(index=index,seed=seed,rows=len(rows),data_sha256=sha(dest),
            context_sha256=sha(dest.with_suffix('.context.bin')),history_sha256=sha(str(base)+'.history.bin'),
            aux_sha256=sha(str(base)+'.aux.bin'),pool_sha256=sha(str(base)+'.pool.bin')))
        (out/'progress.json').write_text(json.dumps(receipts,indent=2)+'\n')
        print(json.dumps(receipts[-1]),flush=True)
    assert sha(binary)==binary_hash
    (out/'complete.json').write_text(json.dumps(receipts,indent=2)+'\n')


if __name__=='__main__':main()
