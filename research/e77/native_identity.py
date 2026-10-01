import sys,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'benchmarks/strength/native'))
from upstream import Upstream,Tracker,stream,sha
from validate import RPC
BIN=ROOT/'local/research/flywheel-target/release/examples/native_policy_worker'
u=Upstream();a=RPC([BIN,ROOT/'research/e68/model/model.bin']);b=RPC([BIN,ROOT/'research/e77/initial.bin']);count=0;root=4503000000;rng=random.Random(77);complete=0
try:
 for game in range(8):
  s=u.setup(stream(root,'setup',game));seat=0;t=Tracker(u,s)
  a.call(op='reset',seed=stream(root,'policy',game),iterations=128,depth=16,search='gumbel')
  b.call(op='reset',seed=stream(root,'policy',game),iterations=128,depth=16,search='gumbel',root_only=True)
  for turn in range(125):
   if u.rewards(s,seat) is not None:complete+=1;break
   o=t.snapshot(s,seat);legal=u.legal(s,seat);x=a.call(op='choose',observation=o,legal=legal);y=b.call(op='choose',observation=o,legal=legal);assert x==y,(game,turn,x,y);assert x['action'] in legal;count+=1
   action=x['action'] if game%2 else rng.choice(legal)
   child,n=u.apply(s,seat,action,stream(root,'chance',game,turn),deterministic=True);t.update(s,child,seat,action);s,seat=child,n
finally:a.close();b.close()
result=dict(games=8,decisions=count,identical_native_actions_and_work=True,complete=complete,binary_sha256=sha(BIN));(ROOT/'research/e77/native-identity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
