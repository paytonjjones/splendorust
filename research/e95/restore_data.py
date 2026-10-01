"""Restore archived teacher rows on this checkout without rerunning the teacher."""
import gzip,hashlib,json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e95';LOCAL=ROOT/'local/research/e95';receipts=json.loads((OUT/'data-archives.json').read_text())
for receipt in receipts:
 split,offset=receipt['split'],receipt['shard'];source=OUT/'data'/split;dest=LOCAL/split/offset;dest.mkdir(exist_ok=True,parents=True)
 for name,info in receipt['files'].items():
  target=dest/name
  if name in ['data.bin','data.context.bin']:
   archive=source/(offset+'-'+name+'.gz');assert sha(archive)==info['archive_sha256']
   if not target.exists():
    with gzip.open(archive,'rb') as compressed,target.open('wb') as f:shutil.copyfileobj(compressed,f)
   assert sha(target)==info['raw_sha256']
  else:
   archive=source/(offset+'-'+name);assert sha(archive)==info['sha256']
   if not target.exists():shutil.copy2(archive,target)
   assert sha(target)==info['sha256']
print(json.dumps(dict(restored_shards=len(receipts),all_raw_hashes_match=True)))

for receipt in json.loads((OUT/'canonical-archives.json').read_text()):
 source=OUT/receipt['archive'];target=ROOT/receipt['restore'];assert sha(source)==receipt['archive_sha256'];target.parent.mkdir(exist_ok=True,parents=True)
 if not target.exists():
  with gzip.open(source,'rb') as compressed,target.open('wb') as f:shutil.copyfileobj(compressed,f)
 assert sha(target)==receipt['raw_sha256']
print(json.dumps(dict(canonical_dependencies_restored=True,all_raw_hashes_match=True)))
