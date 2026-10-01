"""Cache exact public inputs; preserve raw rows and all targets."""
import json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha
sys.path.insert(0,str(ROOT/'research/e86'))
from public_features import batch
start=time.monotonic();out=ROOT/'local/research/e88/data';out.mkdir(exist_ok=True)
receipts=json.loads((ROOT/'research/e88/data-receipts.json').read_text());assert len(receipts)==7
results=[]
for r in receipts:
 source=Path(r['base']);rows=np.memmap(source,mode='r',dtype=DTYPE);ctx=np.memmap(r['context'],mode='r',dtype='<f4',shape=(len(rows),7))
 dest=out/(r['name']+'.bin')
 if dest.exists() or dest.is_symlink():assert dest.resolve()==source.resolve()
 else:dest.symlink_to(source)
 p=dest.with_suffix('.context.bin');features=np.memmap(p,mode='w+',dtype='<f4',shape=(len(rows),911))
 for i in range(0,len(rows),2048):
  mean,public=batch(rows['x'][i:i+2048],ctx[i:i+2048]);features[i:i+2048,:392]=mean;features[i:i+2048,392:]=public
 features.flush();assert np.isfinite(features).all()
 results.append(dict(source=str(source),source_sha256=sha(source),output=str(dest),context=str(p),context_sha256=sha(p),rows=len(rows),label_bytes_unchanged=True))
(ROOT/'research/e88/prepared.json').write_text(json.dumps(dict(seconds=time.monotonic()-start,files=results),indent=2)+'\n')
