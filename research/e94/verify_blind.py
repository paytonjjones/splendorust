"""Extend public-feature invariance to every blind row in the pilot."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'benchmarks/strength/native'));sys.path.insert(0,str(ROOT/'research/e86'))
from upstream import stream
from validate import RPC
from public_features import batch
out=Path(__file__).parent;r=json.loads((out/'histories.json').read_text());rpc=RPC([ROOT/'target/release/examples/native_policy_worker',ROOT/'research/e81/model/model.bin']);count=0;tiers=set();slot_counts=set()
try:
 for game in r['games']:
  for turn,o in enumerate(game['public_observations']):
   op=o['players'][1-o['current']];ctx=np.zeros(7,dtype='<f4')
   for i,v in enumerate(op['reserved'][:op['reserved_count']]):ctx[i]=not v['public'];ctx[i+3]=(v['tier']+1)/3;ctx[6]+=ctx[i]/3
   if ctx[6]==0:continue
   xs=[]
   for repeat in range(8):xs.append(rpc.call(op='sample',observation=o,seed=stream(4830000000,'blind-verify',game['game'],turn*8+repeat))['features'])
   mean,features=batch(np.asarray(xs,dtype='<f4'),np.repeat(ctx[None,:],8,axis=0));assert np.array_equal(mean,np.repeat(mean[:1],8,axis=0));assert np.array_equal(features,np.repeat(features[:1],8,axis=0));count+=1;tiers.update(v['tier'] for v in op['reserved'][:op['reserved_count']] if not v['public']);slot_counts.add(int(ctx[:3].sum()))
finally:rpc.close()
assert count>0
(out/'blind-invariance.json').write_text(json.dumps(dict(blind_observations=count,views_per_observation=8,exact_mean_and_public_feature_invariance=True,unknown_tiers=sorted(tiers),unknown_slot_counts=sorted(slot_counts),scope='Every blind row in eight-game native teacher pilot; no model strength claim'),indent=2)+'\n')
