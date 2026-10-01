"""Recover public metadata with frozen actors and exact saved-state checks."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e86';LOCAL=ROOT/'local/research/e86';BIN=LOCAL/'context-replay-frozen';start=time.monotonic()
jobs=[(f'e82-train-{i:06}',ROOT/f'local/research/e82/train/{i:06}.bin',4580000000+i,ROOT/'research/e81/model/model.bin') for i in range(0,5000,1000)]
jobs += [('e82-dev',ROOT/'local/research/e82/dev.bin',4590000000,ROOT/'research/e81/model/model.bin'),('e81-replay',ROOT/'local/research/e81/train/004000.bin',4300004000,ROOT/'research/e68/model/model.bin')]
plan=dict(binary_sha256=sha(BIN),source_sha256=sha(OUT/'context_replay.rs'),jobs=[dict(name=n,base=str(p),base_sha256=sha(p),seed=s,actor_model_sha256=sha(m)) for n,p,s,m in jobs],script_sha256=sha(__file__),rule='Exact setup/input/mask/outcome check; teacher labels stay original; public metadata only')
(OUT/'reconstruction-plan.json').write_text(json.dumps(plan,indent=2)+'\n');receipts=[]
for name,base,seed,model in jobs:
 output=LOCAL/(name+'.bin');env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(model)
 command=[BIN,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',128,'--actor-agent','flywheel-gumbel','--depth',16,'--threads',14,'--verify-base',base,'--output',output]
 with (OUT/(name+'.log')).open('w') as f:subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 source=output.with_suffix('.context.bin');target=base.with_suffix('.context.bin')
 if target.exists():assert sha(target)==sha(source)
 else:shutil.copy2(source,target)
 shutil.copy2(output.with_suffix('.json'),OUT/(name+'.json'))
 receipts.append(dict(name=name,base=str(base),base_sha256=sha(base),context=str(target),context_sha256=sha(target),context_bytes=target.stat().st_size,verified=True))
 (OUT/'reconstruction-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
(OUT/'reconstruction-completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,files=len(receipts),receipts=receipts),indent=2)+'\n')
