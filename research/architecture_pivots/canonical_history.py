"""Reconstruct history/ground-truth labels and verify the old row bytes."""
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha,DTYPE
import numpy as np


def main():
    local=ROOT/'local/research/architecture-pivots'
    env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e81/model/model.bin')
    jobs=[('train',4680004000,ROOT/'local/research/e87/train/004000.bin',25),
          ('dev',4690000000,ROOT/'local/research/e87/dev.bin',5)]
    receipts=[]
    for split,seed,original,index in jobs:
        dest=local/f'{split}-{index:02d}.canonical.bin'
        cmd=[ROOT/'target/release/examples/flywheel_data','--games',1000,'--seed',seed,
             '--policy-seed',seed+3000000000,'--iterations',800,'--teacher-agent','flywheel-gumbel',
             '--teacher-action-targets','--public-context','--public-history','--depth',16,
             '--threads',4,'--output',dest]
        with (ROOT/f'research/architecture_pivots/{split}-canonical-history.log').open('w') as log:
            subprocess.run(list(map(str,cmd)),env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        assert sha(dest)==sha(original),'canonical replay must preserve the exact old rows'
        manifest=json.loads(dest.with_suffix('.json').read_text())
        assert manifest['complete']==1000 and not manifest['blocked'] and not manifest['capped']
        final_history=local/f'{split}-{index:02d}.history.bin'
        final_aux=local/f'{split}-{index:02d}.aux.bin'
        dest.with_suffix('.history.bin').rename(final_history)
        dest.with_suffix('.aux.bin').rename(final_aux)
        assert final_history.stat().st_size==manifest['rows']*16*32*4
        assert final_aux.stat().st_size==manifest['rows']*8
        receipts.append(dict(split=split,index=index,rows=manifest['rows'],seed=seed,
            exact_row_bytes=True,source_sha256=sha(original),history_sha256=sha(final_history),
            aux_sha256=sha(final_aux),binary_sha256=sha(ROOT/'target/release/examples/flywheel_data'),
            source_id=manifest['source']))
        (ROOT/'research/architecture_pivots/canonical-history-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
        print(json.dumps(receipts[-1]),flush=True)


if __name__=='__main__':main()
