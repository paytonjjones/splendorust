#!/usr/bin/env python3
"""Matched baseline/candidate measurement; never drop unfinished cases."""
import argparse, gzip, hashlib, json, os, platform, statistics, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(x): return json.dumps(x, sort_keys=True, separators=(',', ':')).encode()
def aligned(exe, policy, corpus, threads=1, trace=False):
    command=[str(exe), '--corpus', corpus, '--policy', policy, '--threads', str(threads)]
    if trace: command += ['--trace','--check']
    x=json.loads(subprocess.check_output(command, cwd=ROOT))['samples'][0]
    records=x.pop('records')
    for r in records: r.pop('latency_seconds')
    x['record_set_sha256']=hashlib.sha256(encode(records)).hexdigest()
    return x,records

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--output',required=True);p.add_argument('--repetitions',type=int,default=7);p.add_argument('--threads',type=int,default=1);p.add_argument('--corpus',default='local/play-speed/corpus.json');a=p.parse_args()
    exes={'baseline':ROOT/'local/play-speed/baseline-aligned','candidate':ROOT/a.candidate}
    out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True)
    report={'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'machine':platform.platform(),'cpu':subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),'load_start':os.getloadavg(),'threads':a.threads,'corpus_sha256':sha(ROOT/a.corpus),'binary_sha256':{k:sha(v) for k,v in exes.items()},'source_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'])).hexdigest(),'profile':'seal256-intersection-v1','scope':'existing aligned adapter pipeline; complete canonical enumeration and checked apply','samples':[],'validation':[]}
    def save(): out.write_text(json.dumps(report,indent=2)+'\n')
    for policy in ('random','fixed'):
        b,br=aligned(exes['baseline'],policy,'benchmarks/fixtures/aligned-smoke.json',trace=True)
        c,cr=aligned(exes['candidate'],policy,'benchmarks/fixtures/aligned-smoke.json',trace=True)
        assert br==cr
        report['validation'].append({'policy':policy,'cases':b['count'],'trace_legal_action_outcome_sha256':b['record_set_sha256'],'exact_match':True})
        expected=None
        for rep in range(a.repetitions):
            for name in (('baseline','candidate') if rep%2==0 else ('candidate','baseline')):
                x,records=aligned(exes[name],policy,a.corpus,a.threads)
                if expected is None:
                    expected=x['record_set_sha256']
                    archive=out.with_name(out.stem+'-'+policy+'-records.json.gz')
                    with gzip.open(archive,'wb') as f:f.write(encode(records))
                    report.setdefault('records',{})[policy]={'file':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive)}
                assert x['record_set_sha256']==expected
                x.update(policy=policy,variant=name,repetition=rep,load=os.getloadavg())
                report['samples'].append(x);save()
                print(policy,name,rep,round(x['seconds'],4),flush=True)
    report['summary']={}
    for policy in ('random','fixed'):
        rows={k:[x for x in report['samples'] if x['policy']==policy and x['variant']==k] for k in exes}
        med={k:statistics.median(x['count']/x['seconds'] for x in v) for k,v in rows.items()}
        report['summary'][policy]={'trajectories_per_second':med,'gain_percent':100*(med['candidate']/med['baseline']-1),'seconds_range':{k:[min(x['seconds'] for x in v),max(x['seconds'] for x in v)] for k,v in rows.items()},'exact_records':True}
    report['load_finish']=os.getloadavg();save();print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
