#!/usr/bin/env python3
"""Exact full projected traces against the previous frozen candidate."""
import gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'research/play-speed'))
from measure import aligned,encode
out=ROOT/'research/play-speed/stage2'
corpus='local/play-speed/stage2/trace-corpus.json'
report={'corpus_sha256':hashlib.sha256((ROOT/corpus).read_bytes()).hexdigest(),'master_seed':110000001,'rows':[]}
for policy in ('random','fixed'):
    b,br=aligned(ROOT/'local/play-speed/stage2/baseline-aligned',policy,corpus,trace=True)
    c,cr=aligned(ROOT/'local/play-speed/stage2/final-aligned',policy,corpus,trace=True)
    assert br==cr
    archive=out/(policy+'-traces.json.gz')
    with gzip.open(archive,'wb') as f:f.write(encode(br))
    report['rows'].append({'policy':policy,'cases':b['count'],'decisions':b['decisions'],'turns':b['turns'],'statuses':b['statuses'],'trace_legal_keys_action_keys_outcome_sha256':b['record_set_sha256'],'archive':str(archive.relative_to(ROOT)),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'exact_match':True})
    print(policy,b['count'],b['statuses'],'exact traces match',flush=True)
(out/'TRACES.json').write_text(json.dumps(report,indent=2)+'\n')
