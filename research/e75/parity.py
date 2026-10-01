"""Exact canonical data and native PUCT parity before external Gumbel use."""
import sys,os,json,subprocess,time,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.chdir(ROOT)
sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'benchmarks/strength/native'))
from flywheel_model import sha
from upstream import Upstream,Tracker,stream
from validate import RPC
OUT=ROOT/'research/e75';LOCAL=ROOT/'local/research/e75';LOCAL.mkdir(exist_ok=True)
BIN=ROOT/'target/release/examples';FROZEN=Path('/Users/payton.jones/.codex/worktrees/90ce/splendorust/target/release/examples/native_policy_worker');env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(ROOT/'research/e59/model/model.bin');start=time.monotonic()
for name,flags,wanted in [('legacy',[],'a80e5b35d340356fc8953371e1cb5f13c168ec4a8e3f52bde38c0916da9293a4'),('gumbel',['--actor-iterations',128,'--actor-agent','flywheel-best','--teacher-agent','flywheel-gumbel-noisy'],'83a727477589fc2ee42becca42b960768d7e2454326fe3fb1e940e6c5b266559')]:
 cmd=[BIN/'flywheel_data','--games',16,'--seed',3630000000,'--policy-seed',6630000000,'--iterations',800,'--depth',16,'--threads',14,*flags,'--output',LOCAL/(name+'.bin')]
 with (OUT/(name+'.log')).open('w') as f:subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 assert sha(LOCAL/(name+'.bin'))==wanted,name
u=Upstream();workers=[RPC([b,ROOT/'research/e56/model/model.bin']) for b in [FROZEN,BIN/'native_policy_worker']];choices=0;games=16;root=4450000000;rng=random.Random(75);history=[]
try:
 for game in range(games):
  state=u.setup(stream(root,'setup',game));seat=0;t=Tracker(u,state)
  for rpc in workers:rpc.call(op='reset',seed=stream(root,'policy',game),iterations=128,depth=16)
  trajectory=[]
  for turn in range(125):
   if u.rewards(state,seat) is not None:break
   o=t.snapshot(state,seat);legal=u.legal(state,seat)
   outputs=[rpc.call(op='choose',observation=o,legal=legal) for rpc in workers]
   assert outputs[0]==outputs[1],(game,turn,outputs)
   choices+=1;action=outputs[0]['action'] if game%2 else rng.choice(legal)
   child,next_seat=u.apply(state,seat,action,stream(root,'chance',game,turn),deterministic=True)
   t.update(state,child,seat,action);state,seat=child,next_seat;trajectory.append(action)
  history.append(trajectory)
finally:
 for rpc in workers:rpc.close()
# New mode must be legal, deterministic and budget-exact on public input.
s=u.setup(stream(root,'new',0));t=Tracker(u,s);o=t.snapshot(s,0);legal=u.legal(s,0);rpc=RPC([BIN/'native_policy_worker',ROOT/'research/e68/model/model.bin'])
try:
 outputs=[]
 for _ in range(2):
  rpc.call(op='reset',seed=75,iterations=128,depth=16,search='gumbel');outputs.append(rpc.call(op='choose',observation=o,legal=legal))
 assert outputs[0]==outputs[1] and outputs[0]['action'] in legal and outputs[0]['simulations']==128
finally:rpc.close()
result=dict(canonical_legacy_byte_exact=True,canonical_gumbel_byte_exact=True,native_puct_every_output_exact=True,native_compared_games=games,native_compared_choices=choices,frozen_binary_sha256=sha(FROZEN),new_binary_sha256=sha(BIN/'native_policy_worker'),gumbel_legal_repeatable_exact_budget=True,gumbel_output=outputs[0],trajectories=history,seconds=time.monotonic()-start)
(OUT/'parity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='trajectories'}),flush=True)
