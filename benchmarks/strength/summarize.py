#!/usr/bin/env python3
"""Paired setup bootstrap with bounds for all unfinished games."""
import argparse,collections,hashlib,json,random,statistics
from pathlib import Path

def interval(values,samples=10000):
    rng=random.Random(20260929);n=len(values)
    means=sorted(sum(rng.choices(values,k=n))/n for _ in range(samples))
    return [means[int(samples*.025)],means[int(samples*.975)-1]]

def summarize(path):
    meta,*rows=[json.loads(line) for line in path.read_text().splitlines() if line]
    n=meta.get('players',2)
    if len(rows)!=meta['games'] or len(rows)%n:raise ValueError('incomplete schedule')
    statuses=collections.Counter();blocks=[];seat_stats={str(i):{'games':0,'complete':0,'wins':0,'shared_wins':0,'credit':0.} for i in range(n)}
    native=meta.get('engine')=='seal256_native'
    candidate='seal256_mcts' if native else meta['candidate']
    for i in range(0,len(rows),n):
        pair=rows[i:i+n]
        if len({r['setup_seed'] for r in pair})!=1 or sorted(r['rotation'] for r in pair)!=list(range(n)):
            raise ValueError('invalid setup block')
        if native and meta.get('paired_initial_states'):
            if pair[0]['initial_state']!=pair[1]['initial_state']:raise ValueError('native setup fixture differs between rotations')
        lows=[];highs=[];credits=[];seen=set()
        for r in pair:
            seat=r['seats'].index(candidate);seen.add(seat);s=seat_stats[str(seat)];s['games']+=1
            status=r['status'];rewards=r['rewards']
            if status=='complete' and rewards is not None and sum(rewards)==0:status='native_no_winner'
            statuses[status]+=1;complete=status=='complete'
            if complete:
                if rewards is None or abs(sum(rewards)-1)>1e-8 or any(x<0 or x>1 for x in rewards):raise ValueError('invalid win credit')
                credit=rewards[seat];s['complete']+=1;s['credit']+=credit
                s['wins']+=credit==1;s['shared_wins']+=0<credit<1
            else:credit=None
            credits.append(credit);lows.append(credit if complete else 0);highs.append(credit if complete else 1)
        if seen!=set(range(n)):raise ValueError('candidate seat rotation incomplete')
        blocks.append({'setup_seed':pair[0]['setup_seed'],'credits':credits,'lower':statistics.mean(lows),'upper':statistics.mean(highs)})
    lower=[b['lower'] for b in blocks];upper=[b['upper'] for b in blocks]
    total=sum(s['credit'] for s in seat_stats.values());complete=statuses['complete']
    return {'schema_version':2,'metadata':meta,'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'pairing_verified':not native or meta.get('paired_initial_states',False),
            'games':len(rows),'setup_blocks':len(blocks) if not native or meta.get('paired_initial_states') else None,'statuses':dict(statuses),'incomplete_games':len(rows)-complete,
            'invalid_games':statuses['invalid'],'unsupported_games':statuses['unsupported'],
            'blocked_games':statuses['no_legal_action']+statuses['native_no_winner'],
            'capped_games':statuses['decision_limit']+statuses['capped'],
            'candidate_credit_total':total,'candidate_credit_conditional_rate':total/complete if complete else None,
            'all_requested_credit_bounds':[statistics.mean(lower),statistics.mean(upper)],
            'paired_bootstrap95_missing_envelope':[interval(lower)[0],interval(upper)[1]] if not native or meta.get('paired_initial_states') else None,
            'per_seat':seat_stats,'block_credits':blocks if not native or meta.get('paired_initial_states') else [],
            'reasons':dict(collections.Counter(r.get('reason') for r in rows if r.get('reason'))),
            'interpretation':'Only complete games receive win credit. Resample whole setup blocks. Every missing outcome is bounded [0,1]. Conditional results do not rank unfinished schedules.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(summarize(a.input),indent=2)+'\n')
