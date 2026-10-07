"""Analyze the registered timed round robin without choosing a stopping point."""
import hashlib
import json
import math
import statistics
from pathlib import Path

D = Path(__file__).resolve().parent
plan = json.loads((D / 'PLAN.json').read_text())
rows = [json.loads(line) for line in (D / 'games.jsonl').read_text().splitlines()]
starts = {r['id']: r for r in rows if r.get('type') == 'start'}
ended = {r['record']['id']: r['record'] for r in rows if r.get('type') == 'game'}
assert set(ended) <= set(starts)
assert all(plan['schedule'][i]['seats'] == g['seats'] and plan['schedule'][i]['seed'] == g['seed'] for i,g in ended.items())
replays = {i:g['replay'] for i,g in ended.items()}
for row in rows:
    if row.get('type') == 'turn' and row.get('checkpoint') and row['id'] not in ended:
        replays[row['id']] = row['checkpoint']
(D/'replays.jsonl').write_text(''.join(json.dumps(replays[i])+'\n' for i in sorted(replays)))
pairs = {}
for a,b in [(1,2),(1,8),(2,8)]:
    ids=[i for i,r in starts.items() if sorted(r['seats']) == [a,b]]
    wins=ties=losses=unknown=0
    clusters={}
    for i in ids:
        g=ended.get(i)
        score=None
        if g and not g['stopped'] and g['result'] and g['result']['status']=='finished':
            mask=g['result']['winnerMask']; seat=g['seats'].index(a)
            if mask==3:ties+=1;score=.5
            elif mask & (1<<seat):wins+=1;score=1
            else:losses+=1;score=0
        else:unknown+=1
        clusters.setdefault(starts[i]['seed'],[]).append(score)
    complete=wins+ties+losses
    n=len(ids)
    balanced=[v for v in clusters.values() if len(v)==2 and all(x is not None for x in v)]
    ci=None
    if balanced:
        point=statistics.mean(statistics.mean(v) for v in balanced)
        radius=math.sqrt(math.log(40)/(2*len(balanced)))
        ci=[max(0,point-radius),min(1,point+radius)]
    pairs[f'{a}-{b}']={'lower_batch':a,'higher_batch':b,'started':n,'complete':complete,
        'lower_wins':wins,'ties':ties,'higher_wins':losses,'unknown':unknown,
        'lower_credit_complete_only':(wins+ties*.5)/complete if complete else None,
        'credit_bounds_unknowns':[(wins+ties*.5)/n,(wins+ties*.5+unknown)/n] if n else None,
        'completed_two_seat_setup_pairs':len(balanced),'paired_setup_ci95':ci,
        'lower_batch_seat_counts':[sum(starts[i]['seats'][s]==a for i in ids) for s in (0,1)]}
turns=[r['turn'] for r in rows if r.get('type')=='turn']
cost={}
for batch in [1,2,8]:
    t=[x for x in turns if x['batch']==batch and x['simulations']>0]
    elapsed=sum(x['ms'] for x in t)/1000
    cost[str(batch)]={'searched_turns':len(t),'mean_simulations':statistics.mean(x['simulations'] for x in t) if t else None,
        'median_ms':statistics.median(x['ms'] for x in t) if t else None,
        'simulations_per_second':sum(x['simulations'] for x in t)/elapsed if elapsed else None,
        'ceiling_hits':sum(x['simulations']>=plan['simulation_ceiling'] for x in t),
        'turns_over5s':sum(x['ms']>5000 for x in t),'max_turn_ms':max((x['ms'] for x in t),default=None)}
points={b:[] for b in [1,2,8]}
for p in pairs.values():
    q=p['lower_credit_complete_only']
    if q is not None:
        points[p['lower_batch']].append(q);points[p['higher_batch']].append(1-q)
scores={str(b):statistics.mean(v) if len(v)==2 else None for b,v in points.items()}
valid={b:v for b,v in scores.items() if v is not None}
leaders=[b for b,v in valid.items() if v==max(valid.values())] if valid else []
leader=', '.join(leaders) if leaders else 'unavailable'
summary={'status':'done' if any(r.get('type')=='done' for r in rows) else 'execution_ended_without_done',
    'reserved':len(plan['schedule']),'started':len(starts),'saved_game_records':len(ended),
    'not_started':len(plan['schedule'])-len(starts),'started_without_final_record':sorted(set(starts)-set(ended)),
    'pairs':pairs,'equal_opponent_weighted_credit':scores,'point_estimate_leader':leader,
    'interpretation':'Point estimates are exploratory. Complete-only scores exclude unknowns; uncertainty and incomplete seat rotations must be considered. This test does not automatically promote an engine.',
    'cost':cost,'replay_records':len(replays),'record_sha256':hashlib.sha256((D/'games.jsonl').read_bytes()).hexdigest(),
    'errors':[r for r in rows if r.get('type')=='error']}
(D/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['# One-hour browser batch comparison','',f"The run started {len(starts)} games and saved {len(ended)} game records. {summary['not_started']} reserved games did not start.",'',
    'Both players used the same frozen Entity weights, canonical rules, and a five-second whole-turn limit. The one-billion simulation ceiling was intended not to bind. One hardware WebGPU search ran at a time. The fixed clock cutoff and rotating round robin were registered before outcomes.','',
    '| Matchup | Lower batch wins | Ties | Higher batch wins | Unknown | Complete seat pairs |','| --- | ---: | ---: | ---: | ---: | ---: |']
for key,p in pairs.items():lines.append(f"| {key} | {p['lower_wins']} | {p['ties']} | {p['higher_wins']} | {p['unknown']} | {p['completed_two_seat_setup_pairs']} |")
lines+=['',f"The complete-game point-estimate leader is batch {leader}. This is not a decisive strength claim. See SUMMARY.json for paired setup intervals, seat counts, unknown bounds, and equal-opponent weighted scores. A cycle or wide intervals can leave the ranking unresolved.",'',
    '| Batch | Mean simulations per searched turn | Median searched-turn time |','| --- | ---: | ---: |']
for b,c in cost.items():lines.append(f"| {b} | {c['mean_simulations'] or 0:,.0f} | {(c['median_ms'] or 0)/1000:.3f}s |")
lines+=['','Blocked, capped, or incomplete games have no invented winner. The raw file keeps every start, turn, checkpoint, and final game record. Reserved games not reached are listed separately. Completed-only estimates can be affected by time censoring. Do not infer non-inferiority from a small point lead.','',
    'PLAN.json binds the schedule, source, WASM, model graphs, and budget. backend.json identifies Chrome and hardware WebGPU. batch2-parity.json checks 17 public tensor fixtures and 500 calls. replay-check.log checks saved histories with the native engine. Checks are recorded in the adjacent logs.','',
    'Reproduce analysis with `python3 research/browser-batch-hour-20261007/analyze.py`. Use fresh seeds and a new output directory to run another test. These seeds are consumed evidence.']
(D/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))
