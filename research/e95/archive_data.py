"""Preserve complete teacher rows and replay histories as verified gzip archives."""
import gzip,hashlib,json,shutil,sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e95';LOCAL=ROOT/'local/research/e95';receipts=[]
ap=argparse.ArgumentParser();ap.add_argument('--splits',nargs='+',choices=['train','dev'],default=['train','dev']);args=ap.parse_args()
for split in args.splits:
 count=25 if split=='train' else 5
 dirs=sorted(p for p in (LOCAL/split).glob('[0-9]*') if p.is_dir());assert len(dirs)==count
 dest=OUT/'data'/split;dest.mkdir(exist_ok=True,parents=True)
 for shard in dirs:
  checks=json.loads((shard/'checks.json').read_text());assert checks['games']==checks['completed']==200
  receipt=dict(split=split,shard=shard.name,rows=checks['rows'],files={})
  for name in ['data.bin','data.context.bin']:
   source=shard/name;target=dest/(shard.name+'-'+name+'.gz')
   if not target.exists():
    with target.open('wb') as raw:
     with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
      with source.open('rb') as f:
       for chunk in iter(lambda:f.read(1<<20),b''):compressed.write(chunk)
   h=hashlib.sha256()
   with gzip.open(target,'rb') as f:
    for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
   assert h.hexdigest()==sha(source)
   receipt['files'][name]=dict(raw_sha256=h.hexdigest(),archive_sha256=sha(target),raw_bytes=source.stat().st_size,archive_bytes=target.stat().st_size)
  for name in ['plan.json','checks.json','histories.json.gz']:
   source=shard/name;target=dest/(shard.name+'-'+name)
   if target.exists():assert sha(target)==sha(source)
   else:shutil.copy2(source,target)
   receipt['files'][name]=dict(sha256=sha(target),bytes=target.stat().st_size)
  receipts.append(receipt)
(OUT/'data-archives.json').write_text(json.dumps(receipts,indent=2)+'\n')
print(json.dumps(dict(shards=len(receipts),rows=sum(r['rows'] for r in receipts),exact_decompressed_bytes=True,total_archive_bytes=sum(f.get('archive_bytes',f.get('bytes',0)) for r in receipts for f in r['files'].values()))))
