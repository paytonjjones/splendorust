#!/usr/bin/env python3
"""Full canonical native caller checks and repeated throughput."""
import hashlib,json,os,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    out=ROOT/'research/play-speed/native.json'
    report={'scope':'full-choice published-base native random and native greedy; setup through final digest','samples':[],'binaries':{}}
    for threads in (1,4,8):
        exes={'baseline':ROOT/'local/play-speed/baseline-native','candidate':ROOT/'local/play-speed/final-native'}
        procs={k:subprocess.Popen([str(v),str(threads)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) for k,v in exes.items()}
        for k,p in procs.items():
            report['binaries'][k]={'sha256':hashlib.sha256(exes[k].read_bytes()).hexdigest(),'ready':json.loads(p.stdout.readline())}
        def run(name,q):
            p=procs[name];p.stdin.write(json.dumps(q)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
        for players in ((2,3,4) if threads == 1 else (2,)):
            for workload in ('random','greedy'):
                pilot={'workload':workload,'players':players,'count':1000,'seed':108000001,'check':False}
                b=run('baseline',pilot);c=run('candidate',pilot)
                count=max(1000,min(200000,int(1.2/min(b['seconds'],c['seconds'])*1000)))
                q={**pilot,'count':count}
                for rep in range(7):
                    pair={}
                    for name in (('baseline','candidate') if rep%2==0 else ('candidate','baseline')):
                        x=run(name,q);pair[name]=x
                        report['samples'].append({**x,'threads':threads,'variant':name,'repetition':rep,'load':os.getloadavg()})
                    keys=('digest','decisions','turns','completed','blocked','capped','illegal','simulations')
                    assert all(pair['baseline'][k]==pair['candidate'][k] for k in keys)
                    out.write_text(json.dumps(report,indent=2)+'\n')
                rows={k:[x for x in report['samples'] if x['threads']==threads and x['players']==players and x['workload']==workload and x['variant']==k] for k in exes}
                rates={k:statistics.median(x['count']/x['seconds'] for x in v) for k,v in rows.items()}
                print(threads,players,workload,count,round(100*(rates['candidate']/rates['baseline']-1),2),flush=True)
        for p in procs.values():p.stdin.close();p.wait()
    report['all_counts_and_digests_match']=True
    out.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
