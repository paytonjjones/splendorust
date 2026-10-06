#!/usr/bin/env python3
"""Summarize paired timing noise; this is not a cross-host confidence claim."""
import json,random,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def interval(pairs):
    rng=random.Random(20261006)
    gains=[]
    for _ in range(10000):
        chosen=[rng.choice(pairs) for _ in pairs]
        gains.append(100*(statistics.median(b for b,c in chosen)/statistics.median(c for b,c in chosen)-1))
    gains.sort();return [gains[249],gains[9749]]
def main():
    p=ROOT/'research/play-speed/confirmation.json';x=json.loads(p.read_text())
    for policy in ('random','fixed'):
        rows=[s for s in x['samples'] if s['policy']==policy]
        pairs=[tuple(next(s['seconds'] for s in rows if s['repetition']==rep and s['variant']==variant) for variant in ('baseline','candidate')) for rep in range(7)]
        x['summary'][policy]['paired_bootstrap95_gain_percent']=interval(pairs)
    x['uncertainty']={'seed':20261006,'resamples':10000,'method':'paired repetition bootstrap of median elapsed-time ratio; shared host machine noise only'}
    p.write_text(json.dumps(x,indent=2)+'\n')
    p=ROOT/'research/play-speed/native.json';n=json.loads(p.read_text());n['summary']=[]
    configs=sorted(set((s['threads'],s['players'],s['workload']) for s in n['samples']))
    for threads,players,workload in configs:
        rows=[s for s in n['samples'] if (s['threads'],s['players'],s['workload'])==(threads,players,workload)]
        pairs=[tuple(next(s['seconds'] for s in rows if s['repetition']==rep and s['variant']==variant) for variant in ('baseline','candidate')) for rep in range(7)]
        rates={variant:statistics.median(s['count']/s['seconds'] for s in rows if s['variant']==variant) for variant in ('baseline','candidate')}
        n['summary'].append({'threads':threads,'players':players,'workload':workload,'gain_percent':100*(rates['candidate']/rates['baseline']-1),'rates':rates,'paired_bootstrap95_gain_percent':interval(pairs),'minimum_seconds':min(s['seconds'] for s in rows),'count':rows[0]['count'],'completed':rows[0]['completed'],'blocked':rows[0]['blocked'],'capped':rows[0]['capped'],'digest':rows[0]['digest']})
    n['uncertainty']=x['uncertainty'];p.write_text(json.dumps(n,indent=2)+'\n')
    print(json.dumps({'aligned':x['summary'],'native':n['summary']},indent=2))
if __name__=='__main__':main()
