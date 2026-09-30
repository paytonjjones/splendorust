import hashlib,json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
os.chdir(root)
output=root/'local/research/e44-scaling';output.mkdir(parents=True,exist_ok=False)
env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(root/'local/research/flywheel-e40/cycle-000/model/model.bin');env['SPLENDOR_CANDIDATE_MODEL']=str(root/'research/e30/model.bin')
binary=root/'local/research/flywheel-target/release/splendor'
data=binary.parent/'examples/flywheel_data'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=dict(games=256,iterations=128,depth=16,threads=[4,8,12,14],binary_sha256=sha(binary),data_binary_sha256=sha(data),teacher_sha256=sha(Path(env['SPLENDOR_BEST_MODEL'])),candidate_sha256=sha(Path(env['SPLENDOR_CANDIDATE_MODEL'])),started=time.time(),host='14 CPU cores, 48 GiB; serial jobs, no competing arena')
(output/'plan.json').write_text(json.dumps(manifest,indent=2))
results=[]
for repeat,order in enumerate(([4,8,12,14],[14,12,8,4])):
    expected={}
    for threads in order:
        for stage in ['selfplay','arena']:
            prefix=output/f'{stage}-r{repeat}-t{threads}'
            if stage=='selfplay':
                dest=prefix.with_suffix('.bin');cmd=[data,'--games',256,'--seed',1100000000+repeat*1000000,'--policy-seed',4100000000+repeat*1000000,'--iterations',128,'--depth',16,'--threads',threads,'--output',dest]
            else:
                dest=prefix.with_suffix('.json');cmd=[binary,'compare','--agent-a','flywheel-candidate','--agent-b','flywheel-best','--games',256,'--seed',1120000000+repeat*1000000,'--iterations',128,'--depth',16,'--threads',threads,'--output',dest]
            start=time.monotonic()
            with prefix.with_suffix('.log').open('w') as log:
                proc=subprocess.run(list(map(str,cmd)),env=env,stdout=log,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-start
            report=json.loads(dest.with_suffix('.json').read_text())
            fingerprint=sha(dest) if stage=='selfplay' else hashlib.sha256(json.dumps(report['records'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if stage in expected:assert expected[stage]==fingerprint,'thread determinism failed'
            expected[stage]=fingerprint
            row=dict(stage=stage,repeat=repeat,threads=threads,wall_seconds=elapsed,games_per_second=256/elapsed,record_or_data_sha256=fingerprint,exit_code=proc.returncode)
            if stage=='selfplay':row.update(positions=report['rows'],positions_per_second=report['rows']/elapsed)
            results.append(row);print(json.dumps(row),flush=True)
            (output/'results.json').write_text(json.dumps(dict(plan=manifest,results=results),indent=2))
