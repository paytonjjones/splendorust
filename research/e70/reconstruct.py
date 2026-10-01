"""Recover public metadata with frozen actors and exact saved-state checks."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e70';LOCAL=ROOT/'local/research/e70';BIN=LOCAL/'context-replay-frozen';start=time.monotonic()
assert sha(ROOT/'research/e59/model/model.bin')=='76d45006d332dcd80635150f23917c321245f49cfb10a8e77654d3096505a918'
env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin')
jobs=[(f'e68-train-{i:06}',ROOT/f'local/research/e68/train/{i:06}.bin',4210000000+i,128) for i in range(0,5000,1000)]
jobs += [('e68-dev',ROOT/'local/research/e68/dev.bin',4220000000,128),('e64-replay',ROOT/'local/research/e64/train.bin',3630000000,800)]
plan=dict(binary_sha256=sha(BIN),model_sha256=sha(ROOT/'research/e59/model/model.bin'),source_sha256=sha(ROOT/'crates/splendor-arena/examples/context_replay.rs'),jobs=[dict(name=n,base=str(p),base_sha256=sha(p),seed=s,iterations=b) for n,p,s,b in jobs],script_sha256=sha(__file__),rule='Exact setup/input/mask/outcome check; teacher labels remain original; public metadata only')
(OUT/'reconstruction-plan.json').write_text(json.dumps(plan,indent=2)+'\n');shutil.copy2(ROOT/'crates/splendor-arena/examples/context_replay.rs',OUT/'context_replay.rs')
receipts=[]
for name,base,seed,budget in jobs:
 output=LOCAL/(name+'.bin')
 command=[BIN,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',budget,'--depth',16,'--threads',14,'--verify-base',base,'--output',output]
 with (OUT/(name+'.log')).open('w') as f:subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 source=output.with_suffix('.context.bin');target=base.with_suffix('.context.bin');assert not target.exists();shutil.copy2(source,target)
 shutil.copy2(output.with_suffix('.json'),OUT/(name+'.json'))
 receipts.append(dict(name=name,base=str(base),base_sha256=sha(base),context=str(target),context_sha256=sha(target),context_bytes=target.stat().st_size,verified=True))
 (OUT/'reconstruction-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
(OUT/'reconstruction-completed.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,files=len(receipts),receipts=receipts),indent=2)+'\n')
