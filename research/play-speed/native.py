#!/usr/bin/env python3
"""Full canonical native caller checks and repeated throughput."""
import argparse,hashlib,json,os,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',default='local/play-speed/baseline-native')
    parser.add_argument('--candidate',default='local/play-speed/final-native')
    parser.add_argument('--output',default='research/play-speed/native.json')
    parser.add_argument('--players',nargs='+',type=int,default=[2,3,4])
    parser.add_argument('--threads',nargs='+',type=int,default=[1,4,8])
    parser.add_argument('--target-seconds',type=float,default=1.2)
    parser.add_argument('--max-count',type=int,default=200000)
    args=parser.parse_args()
    out=ROOT/args.output
    report={'settings':vars(args),'scope':'full-choice published-base native random and native greedy; setup through final digest','samples':[],'binaries':{}}
    for threads in args.threads:
        exes={'baseline':ROOT/args.baseline,'candidate':ROOT/args.candidate}
        procs={k:subprocess.Popen([str(v),str(threads)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) for k,v in exes.items()}
        for k,p in procs.items():
            report['binaries'][k]={'sha256':hashlib.sha256(exes[k].read_bytes()).hexdigest(),'ready':json.loads(p.stdout.readline())}
        def run(name,q):
            p=procs[name];p.stdin.write(json.dumps(q)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
        for players in (args.players if threads == 1 else [2]):
            for workload in ('random','greedy'):
                pilot={'workload':workload,'players':players,'count':1000,'seed':108000001,'check':False}
                b=run('baseline',pilot);c=run('candidate',pilot)
                count=max(1000,min(args.max_count,int(args.target_seconds/min(b['seconds'],c['seconds'])*1000)))
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
