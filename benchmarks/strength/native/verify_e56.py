#!/usr/bin/env python3
"""Verify frozen E56 evidence without changing the current native workflow."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'e56-frozen'
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for data in iter(lambda:f.read(1<<20),b''):h.update(data)
 return h.hexdigest()
def main():
 manifest=json.loads((ROOT/'artifact-manifest.json').read_text())
 for name,expected in manifest['file_sha256'].items():assert digest(ROOT/name)==expected,name
 index=json.loads((ROOT/'archive-index.json').read_text())
 for item in index['files']:
  p=ROOT/item['path'];assert digest(p)==item['gzip_sha256'];h=hashlib.sha256();n=0
  with gzip.open(p,'rb') as f:
   for data in iter(lambda:f.read(1<<20),b''):h.update(data);n+=len(data)
  assert h.hexdigest()==item['raw_sha256'] and n==item['raw_bytes'],item['path']
 result=dict(profile=manifest['profile'],artifacts_verified=len(manifest['file_sha256']),lossless_archives_verified=len(index['files']),scope='Static hashes and lossless decompression; prior replay receipts preserved, no policy rerun')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
