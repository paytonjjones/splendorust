import sys,json,hashlib,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from collect_evidence import interval
p=Path('research/e80/arena.jsonl');meta,*rows=[json.loads(s) for s in p.read_text().splitlines()]
assert len(rows)==2000 and meta['games']==2000
assert [(r['block'],r['rotation']) for r in rows]==[(i//2,i%2) for i in range(2000)]
for a,b in zip(rows[::2],rows[1::2]):assert a['setup']==b['setup']
complete=[r for r in rows if r['status']=='complete'];missing=len(rows)-len(complete);credit=sum(r['policy_argmax_credit'] for r in complete)
lo=[sum(r['policy_argmax_credit'] or 0 for r in rows[i:i+2])/2 for i in range(0,2000,2)]
hi=[sum(1 if r['policy_argmax_credit'] is None else r['policy_argmax_credit'] for r in rows[i:i+2])/2 for i in range(0,2000,2)]
decisions=sum(r['teacher_decisions'] for r in rows)
result=dict(requested=2000,complete=len(complete),status_counts={status:sum(r['status']==status for r in rows) for status in {r['status'] for r in rows}},policy_argmax_credit=credit/len(complete) if complete else None,requested_credit_bounds=[credit/2000,(credit+missing)/2000],ci95=[interval(lo)[0],interval(hi)[1]],teacher_decisions=decisions,selected_argmax_agreement=sum(r['selected_argmax_agreements'] for r in rows)/decisions,mean_selected_target_probability=sum(r['selected_target_probability_sum'] for r in rows)/decisions,seconds=meta['seconds'],raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rule='diagnostic only; no model promotion; missing outcomes remain unknown',conclusion='target-action teacher is materially weaker' if missing==0 and interval(hi)[1]<.5 else 'target-action weakness not established')
Path('research/e80/summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
