"""Require old-model native policy and sampling identity after format expansion."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'benchmarks/strength/native'));sys.path.insert(0,str(ROOT/'research'))
from validate import RPC
from upstream import sha
old=ROOT/'local/research/e92/frozen/native_policy_worker';new=ROOT/'local/research/flywheel-target/release/examples/native_policy_worker';model=ROOT/'research/e81/model/model.bin';r=json.loads((ROOT/'research/e94/histories.json').read_text());workers=[RPC([p,model]) for p in [old,new]];n=0
try:
 for game in r['games']:
  for p in workers:p.call(op='reset',seed=4890000000+game['game'],iterations=128,depth=16,search='gumbel',root_only=False)
  for turn,o in enumerate(game['public_observations'][:16]):
   samples=[p.call(op='sample',observation=o,seed=4890001000+turn) for p in workers];assert samples[0]==samples[1]
   # Recover the exact native legal mask from the frozen pilot row sequence.
   from upstream import Upstream,Tracker
   if turn==0:u=Upstream();state=u.setup(game['setup']);tracker=Tracker(u,state);seat=0
   assert tracker.snapshot(state,seat)==o
   legal=u.legal(state,seat);answers=[p.call(op='choose',observation=o,legal=legal) for p in workers];assert answers[0]==answers[1];n+=1
   child,next_seat=u.apply(state,seat,game['actions'][turn],game['chance_seeds'][turn]);tracker.update(state,child,seat,game['actions'][turn]);state,seat=child,next_seat
finally:
 for p in workers:p.close()
(ROOT/'research/e95/legacy-native-parity.json').write_text(json.dumps(dict(decisions=n,exact_actions_work_counts_and_sample_bytes=True,old_worker_sha256=sha(old),new_worker_sha256=sha(new),model_sha256=sha(model)),indent=2)+'\n')
