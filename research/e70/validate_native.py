"""Native public-context cost, legal-play and raw-data compatibility checks."""
import os,sys,json,subprocess,time,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
import numpy as np
OUT=ROOT/'research/e70';LOCAL=ROOT/'local/research/e70';BIN=ROOT/'local/research/flywheel-target/release';env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin');start=time.monotonic()
def run(cmd,name):
 with (OUT/name).open('w') as f:subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
run([BIN/'examples/transfer_parity',OUT/'zero.bin',OUT/'zero-parity.json','real'],'zero-parity-final.log')
for flag,name in [([], 'legacy'),(['--public-context'],'context')]:
 run([BIN/'examples/flywheel_data','--games',16,'--seed',3630000000,'--policy-seed',6630000000,'--iterations',800,'--depth',16,'--threads',14,*flag,'--output',LOCAL/(name+'.bin')],name+'-collection.log')
 assert sha(LOCAL/(name+'.bin'))=='a80e5b35d340356fc8953371e1cb5f13c168ec4a8e3f52bde38c0916da9293a4'
c=np.fromfile(LOCAL/'context.context.bin',dtype='<f4').reshape(-1,7)
assert len(c)==934 and np.isfinite(c).all() and ((c>=0)&(c<=1)).all() and c[:,:3].sum()>0
reconstructed=np.fromfile(ROOT/'local/research/e64/train.context.bin',dtype='<f4').reshape(-1,7)
assert np.array_equal(c,reconstructed[:len(c)])
env['SPLENDOR_CANDIDATE_MODEL']=str(OUT/'zero.bin')
run([BIN/'splendor','compare','--agent-a','flywheel-candidate','--agent-b','strong','--games',16,'--players',2,'--seed',4280000000,'--threads',14,'--iterations',128,'--depth',16,'--check','--output',OUT/'legal-play.json'],'legal-play.log')
r=json.loads((OUT/'legal-play.json').read_text());assert r['requested_games']==16 and all(x['status']=='complete' for x in r['records'])
timings={}
for name,model in [('old',ROOT/'research/e59/model/model.bin'),('context',OUT/'zero.bin'),('old-repeat',ROOT/'research/e59/model/model.bin')]:
 run([BIN/'examples/transfer_latency',model,OUT/'zero-parity.json',OUT/(name+'-outputs.json')],name+'-latency.log')
 timings[name]=[json.loads(s)['seconds']/10000 for s in (OUT/(name+'-latency.log')).read_text().splitlines()]
outputs=[json.loads((OUT/(n+'-outputs.json')).read_text()) for n in ['old','context']]
assert outputs[0]==outputs[1],'zero columns changed native function'
result=dict(default_raw_byte_exact=True,optional_context_raw_byte_exact=True,context_matches_reconstruction_exact=True,context_rows=len(c),legal_complete_games=16,initial_native_outputs_exact=True,inference_seconds=timings,context_cost_ratio=statistics.median(timings['context'])/statistics.median(timings['old']+timings['old-repeat']),timing_scope='Shared host; fixed 64 observation fixture, alternating old/context/old, 3x10k calls each. Not a strength test.',seconds=time.monotonic()-start)
(OUT/'native-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
