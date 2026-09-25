#!/usr/bin/env python3
"""Archive completed runs and emit compact summaries with corrected two-sided CIs."""
import gzip
import hashlib
import json
import math
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'docs/results'
out.mkdir(parents=True,exist_ok=True)

def interval(xs):
    if len(xs)<2:return [0,1]
    n=len(xs);mean=sum(xs)/n;var=sum((x-mean)**2 for x in xs)/(n-1)
    log=math.log(4/0.05);half=math.sqrt(2*var*log/n)+7*log/(3*(n-1))
    return [max(0,mean-half),min(1,mean+half)]

paths=list((ROOT/'results').glob('*.json'))+list((ROOT/'results/promotion').glob('*.json'))
index=[]
for path in sorted(paths):
    raw=path.read_bytes();r=json.loads(raw)
    if 'records' not in r:continue
    name=('promotion-' if path.parent.name=='promotion' else '')+path.stem
    # Preserve raw evidence byte for byte. Early experiments used a one-sided
    # alpha setting; compact summaries recompute the proper two-sided interval.
    (out/(name+'.json.gz')).write_bytes(gzip.compress(raw,mtime=0))
    records=r.pop('records');n=r['players']
    for agent in r['agents']:
        def credits(unknown):
            result=[]
            for start in range(0,len(records),n):
                total=0
                for g in records[start:start+n]:
                    if g['status']!='complete':total+=unknown;continue
                    seat=g['seats'].index(agent['identity'])
                    if g['winners']&(1<<seat):total+=1/g['winners'].bit_count()
                result.append(total/n)
            return result
        agent['ci95']=[interval(credits(0))[0],interval(credits(1))[1]]
    r['ci_method']='Two-sided 95% empirical Bernstein over setup blocks, alpha/2 per tail; missing outcomes bounded by 0 and 1'
    r['raw_report_sha256']=hashlib.sha256(raw).hexdigest()
    r['record_set_sha256']=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    r['raw_archive']=name+'.json.gz'
    r['summary_note']='Intervals recomputed by scripts/collect_evidence.py; raw historical reports preserved unchanged.'
    r['status_counts']={k:sum(g['status']==k for g in records) for k in sorted(set(g['status'] for g in records))}
    (out/(name+'.summary.json')).write_text(json.dumps(r,indent=2)+'\n')
    index.append({'name':name,'games':r['requested_games'],'completed':r['completed_games'],'seed':r['seed'],'players':n,'candidate':r['agents'][0]['agent'],'opponent':r['agents'][1]['agent'],'credit':r['agents'][0]['win_rate'],'ci95':r['agents'][0]['ci95'],'seconds':r['runtime_seconds'],'records_sha256':r['record_set_sha256']})
(out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
print(f'Archived {len(index)} reports.')
