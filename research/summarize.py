#!/usr/bin/env python3
"""Validate research reports and preserve counts, intervals and file hashes."""
import collections,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_evidence import validate_report,record_interval
rows=[]
for file in sorted(Path(sys.argv[1]).glob('*.json')):
    if file.name == 'summary.json': continue
    r=json.loads(file.read_text())
    if 'records' not in r: continue
    validate_report(r)
    rows.append({'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'source':r['source_id'],'statuses':dict(collections.Counter(x['status'] for x in r['records'])),'agents':r['agents'],'interval':record_interval(r['records'],r['players'],0),'seconds':r['runtime_seconds'],'decisions_per_second':r['decisions_per_second'],'record_set_sha256':hashlib.sha256(json.dumps(r['records'],sort_keys=True,separators=(',',':')).encode()).hexdigest()})
print(json.dumps(rows,indent=2))
