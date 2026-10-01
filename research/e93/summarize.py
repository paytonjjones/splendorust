import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from collect_evidence import interval
out=Path(__file__).parent;p=out/'arena.jsonl';meta,*rows=[json.loads(s) for s in p.read_text().splitlines()]
assert meta['games']==2000 and len(rows)==2000
assert [(r['block'],r['rotation']) for r in rows]==[(i//2,i%2) for i in range(2000)]
for a,b in zip(rows[::2],rows[1::2]):assert a['setup']==b['setup']
for r in rows:
 assert r['ensemble_simulations']==800*r['ensemble_main_decisions']
 assert (r['consensus_credit'] is not None)==(r['status']=='complete')
complete=[r for r in rows if r['status']=='complete'];missing=2000-len(complete);credit=sum(r['consensus_credit'] for r in complete)
lo=[sum(r['consensus_credit'] or 0 for r in rows[i:i+2])/2 for i in range(0,2000,2)]
hi=[sum(1 if r['consensus_credit'] is None else r['consensus_credit'] for r in rows[i:i+2])/2 for i in range(0,2000,2)]
ci=[interval(lo)[0],interval(hi)[1]];decisions=sum(r['ensemble_main_decisions'] for r in rows)
s=dict(requested=2000,completed=len(complete),status_counts={status:sum(r['status']==status for r in rows) for status in sorted(set(r['status'] for r in rows))},consensus_credit_among_complete=credit/len(complete) if complete else None,requested_credit_bounds=[credit/2000,(credit+missing)/2000],ci95=ci,ensemble_main_decisions=decisions,vote_tie_rate=sum(r['vote_ties'] for r in rows)/decisions,first_replica_agreement=sum(r['first_replica_agreements'] for r in rows)/decisions,mean_max_vote_fraction=sum(r['max_vote_sum'] for r in rows)/(4*decisions),seconds=meta['seconds'],ensemble_simulations=sum(r['ensemble_simulations'] for r in rows),single_simulations=sum(r['single_simulations'] for r in rows),raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='Equal total simulations: four E88 root-Gumbel200 teachers versus single800; four root evaluations can add wall cost; no model promotion',decision='consensus direction passes teacher-quality test' if missing==0 and ci[0]>.5 else 'do not collect expensive consensus corpus: benefit not established')
(out/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))
