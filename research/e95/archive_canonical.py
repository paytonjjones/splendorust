"""Archive the exact canonical replay/development dependencies for E95."""
import gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
OUT=ROOT/'research/e95';dest=OUT/'data/canonical';dest.mkdir(exist_ok=True,parents=True);receipts=[]
for label,relative in [('replay','local/research/e87/train/004000'),('dev','local/research/e87/dev')]:
 for suffix in ['.bin','.context.bin']:
  source=ROOT/(relative+suffix);target=dest/(label+suffix+'.gz')
  if not target.exists():
   with target.open('wb') as raw:
    with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
     with source.open('rb') as f:
      for chunk in iter(lambda:f.read(1<<20),b''):compressed.write(chunk)
  h=hashlib.sha256()
  with gzip.open(target,'rb') as f:
   for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
  assert h.hexdigest()==sha(source)
  receipts.append(dict(archive=str(target.relative_to(OUT)),restore=str(source.relative_to(ROOT)),raw_sha256=h.hexdigest(),archive_sha256=sha(target),raw_bytes=source.stat().st_size,archive_bytes=target.stat().st_size))
(OUT/'canonical-archives.json').write_text(json.dumps(receipts,indent=2)+'\n');print(json.dumps(dict(files=len(receipts),exact_decompressed_bytes=True,compressed_bytes=sum(r['archive_bytes'] for r in receipts))))
