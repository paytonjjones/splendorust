"""Continue the E88 attention lineage with fresh strong-policy self-play."""
import json,os,shutil,subprocess,sys,time,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT);sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha,DTYPE
from lineage import provisional_decision
sys.path.insert(0,str(ROOT/'research/e86'))
from public_features import batch
OUT=ROOT/'research/e89';LOCAL=ROOT/'local/research/e89';BIN=ROOT/'local/research/flywheel-target/release';BASE=ROOT/'research/e88/model';CHAMP=ROOT/'research/e81/model'
EXPECTED='095020d9adb9f1d60978a19ac754fe21477d700e54c0afcac3cbee28c31b4331'
assert sha(BASE/'model.bin')==EXPECTED
assert not (OUT/'plan.json').exists(),'immutable experiment'
start=time.monotonic();env=os.environ.copy();env.update(SPLENDOR_BEST_MODEL=str(BASE/'model.bin'),CARGO_TARGET_DIR=str(ROOT/'local/research/flywheel-target'),CARGO_BUILD_JOBS='2')
def run(command,name,allowed=(0,)):
 with (OUT/name).open('w') as f:r=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
 if r.returncode not in allowed:raise RuntimeError(f'{name}: exit {r.returncode}')
collector=LOCAL/'collector-frozen';shutil.copy2(BIN/'examples/flywheel_data',collector)
plan=dict(schema='attention-lineage-fullgame-v1',parent_sha256=EXPECTED,parent_checkpoint_sha256=sha(BASE/'model.pt'),champion_sha256=sha(CHAMP/'model.bin'),collector_sha256=sha(collector),collector_source_sha256=sha(ROOT/'crates/splendor-arena/examples/flywheel_data.rs'),actor_agent='flywheel-root-gumbel-best',teacher_agent='flywheel-root-gumbel-best',actor_iterations=800,teacher_iterations=800,teacher_action_targets=True,threads=14,depth=16,train_games=5000,dev_games=1000,train_seed=4730000000,dev_seed=4740000000,screen_seed=4750000000,champion_check_seed=4760000000,training_seed=800000021,epochs=10,replay_source=str(ROOT/'local/research/e87/train/004000.bin'),replay_sha256=sha(ROOT/'local/research/e87/train/004000.bin'),scripts={n:sha(OUT/n) for n in ['run.py','train.py','attention_model.py']},frozen_public_features_sha256=sha(ROOT/'research/e86/public_features.py'),selection='worst-case requested credit >50.5%; champion unchanged')
(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');shutil.copy2(ROOT/'crates/splendor-arena/examples/flywheel_data.rs',OUT/'flywheel_data.rs')
data=LOCAL/'data';data.mkdir(exist_ok=True);receipts=[]
def prepare(source,context,name):
 dest=data/(name+'.bin');dest.symlink_to(source);rows=np.memmap(source,mode='r',dtype=DTYPE);ctx=np.memmap(context,mode='r',dtype='<f4',shape=(len(rows),7));cached=dest.with_suffix('.context.bin');features=np.memmap(cached,mode='w+',dtype='<f4',shape=(len(rows),911))
 for i in range(0,len(rows),2048):
  mean,public=batch(rows['x'][i:i+2048],ctx[i:i+2048]);features[i:i+2048,:392]=mean;features[i:i+2048,392:]=public
 features.flush();assert np.isfinite(features).all()
 receipts.append(dict(source=str(source),data_sha256=sha(source),raw_context_sha256=sha(context),cached_context_sha256=sha(cached),rows=len(rows),label_bytes_unchanged=True))
 (OUT/'data-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n');return dest
train=[]
for offset in range(0,5000,1000):
 path=LOCAL/'train'/f'{offset:06}.bin';path.parent.mkdir(parents=True,exist_ok=True);seed=4730000000+offset
 run([collector,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',800,'--teacher-agent','flywheel-root-gumbel-best','--teacher-action-targets','--public-context','--depth',16,'--threads',14,'--output',path],f'train-{offset:06}.log')
 shutil.copy2(path.with_suffix('.json'),OUT/f'train-{offset:06}.json');train.append(prepare(path,path.with_suffix('.context.bin'),f'train-{offset:06}'))
 (OUT/'progress.json').write_text(json.dumps(dict(stage='collection',completed_train_games=offset+1000,seconds=time.monotonic()-start),indent=2)+'\n')
source=Path(plan['replay_source']);train.append(prepare(source,source.with_suffix('.context.bin'),'replay'))
path=LOCAL/'dev.bin';seed=4740000000
run([collector,'--games',1000,'--seed',seed,'--policy-seed',seed+3000000000,'--iterations',800,'--teacher-agent','flywheel-root-gumbel-best','--teacher-action-targets','--public-context','--depth',16,'--threads',14,'--output',path],'dev.log')
shutil.copy2(path.with_suffix('.json'),OUT/'dev.json');dev=prepare(path,path.with_suffix('.context.bin'),'dev')
assert all(sha(OUT/n)==h for n,h in plan['scripts'].items()) and sha(source)==plan['replay_sha256']
run([sys.executable,OUT/'train.py','--architecture','attention-residual','--public-context','--residual-width',64,'--residual-blocks',2,'--warmstart',BASE/'model.pt','--train',*train,'--dev',dev,'--output',OUT/'model','--epochs',10,'--batch-size',1024,'--seed',800000021],'training.log')
model=OUT/'model';m=json.loads((model/'manifest.json').read_text());assert sha(model/'base.bin')==plan['champion_sha256']
f=json.loads((model/'parity.json').read_text());f['context']=[r[-7:] for r in f['context']];(model/'parity-public.json').write_text(json.dumps(f)+'\n')
run([BIN/'examples/transfer_parity',model/'model.bin',model/'parity-public.json','real'],'native-parity.log')
# Cost remains relative to the confirmed E81 endpoint, not the slower provisional parent.
env['SPLENDOR_BEST_MODEL']=str(CHAMP/'model.bin');env['SPLENDOR_CANDIDATE_MODEL']=str(model/'model.bin')
run([ROOT/'local/research/e88-cost'],'cost.jsonl')
rows=[json.loads(s) for s in (OUT/'cost.jsonl').read_text().splitlines()];ratios=[]
for i in range(3):
 a=next(r for r in rows if r['repeat']==i and 'candidate' in r['agent']);b=next(r for r in rows if r['repeat']==i and 'candidate' not in r['agent']);assert a['simulations']==b['simulations']==568*128;ratios.append(a['seconds']/b['seconds'])
cost=dict(ratios=ratios,median_ratio=statistics.median(ratios),limit=1.15,shared_host=True);cost['passes']=cost['median_ratio']<=1.15;(OUT/'cost-summary.json').write_text(json.dumps(cost,indent=2)+'\n');assert cost['passes']
if m['model_sha256']==EXPECTED:decision=dict(selected=False,reason='unchanged endpoint; skip arena')
else:
 env['SPLENDOR_BEST_MODEL']=str(BASE/'model.bin')
 run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-root-gumbel-candidate','--baseline','flywheel-root-gumbel-best','--screen',2000,'--confirm',0,'--seed',4750000000,'--threads',14,'--iterations',128,'--depth',16,'--output',OUT/'gate'],'gate.log',(0,2))
 decision=provisional_decision(json.loads((OUT/'gate/screen.json').read_text()));decision['strict_decision']=json.loads((OUT/'gate/decision.json').read_text())
 if decision['selected']:
  env['SPLENDOR_BEST_MODEL']=str(CHAMP/'model.bin')
  run([sys.executable,ROOT/'scripts/promote.py','--candidate','flywheel-root-gumbel-candidate','--baseline','flywheel-gumbel','--screen',2000,'--confirm',0,'--seed',4760000000,'--threads',14,'--iterations',128,'--depth',16,'--output',OUT/'champion-check'],'champion-check.log',(0,2))
decision.update(parent_sha256=EXPECTED,candidate_sha256=m['model_sha256'],champion_unchanged=True)
(OUT/'decision.json').write_text(json.dumps(decision,indent=2)+'\n');assert sha(CHAMP/'model.bin')==plan['champion_sha256']
(OUT/'completed.json').write_text(json.dumps(dict(decision=decision,seconds=time.monotonic()-start),indent=2)+'\n');print(json.dumps(decision),flush=True)
