"""Finish the owned timed run even while the chat is idle."""
import datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
D=Path(__file__).resolve().parent
ROOT=D.parents[1]
owned_pid=int(sys.argv[1])
plan=json.loads((D/'PLAN.json').read_text())
end=datetime.datetime.fromisoformat(plan['play_cutoff_utc'].replace('Z','+00:00')).timestamp()+30
while time.time()<end:
    try:os.kill(owned_pid,0)
    except ProcessLookupError:break
    time.sleep(2)
else:
    data=subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()
    tree={int(a[0]):int(a[1]) for r in data if len(a:=r.split())==2}
    children={owned_pid}
    while True:
        added={p for p,pp in tree.items() if pp in children}
        if added<=children:break
        children|=added
    for p in sorted(children,reverse=True):
        try:os.kill(p,15)
        except ProcessLookupError:pass
result={'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_matches_plan':all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest for f,digest in plan['source_sha256'].items())}
for name,command in [('analysis',['python3',str(D/'analyze.py')]),('replay',['cargo','run','--release','--locked','-p','splendor-arena','--example','validate_web_records','--',str(D/'replays.jsonl')])]:
    with (D/f'{name}-check.log').open('w') as log:
        try:
            remaining=datetime.datetime.fromisoformat(plan['report_deadline_utc'].replace('Z','+00:00')).timestamp()-time.time()-1
            run=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=max(1,min(180,remaining)))
            code=run.returncode
        except subprocess.TimeoutExpired:
            code=124
    result[name+'_exit_code']=code
result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(D/'FINISHED.json').write_text(json.dumps(result,indent=2)+'\n')
