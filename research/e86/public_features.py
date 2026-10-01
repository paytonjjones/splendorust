"""Batched public mean inputs and519-feature belief inputs."""
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research/e85'))
from belief import CARDS,COLORS,GROUP,SLOT,moments
TIER=np.array([int(c['tier'])-1 for c in CARDS]);GROUP=np.array(GROUP);SLOT=np.array(SLOT)
COST=np.array([[int(c[k]) for k in COLORS] for c in CARDS],dtype=np.float64)
BONUS=np.array([[int(c['bonus']==k) for k in COLORS] for c in CARDS],dtype=np.float64)
POINTS=np.array([int(c['points']) for c in CARDS],dtype=np.float64)
def batch(x,context):
 x=np.asarray(x,dtype=np.float32);context=np.asarray(context,dtype=np.float32);b=len(x)
 pool=((x[:,(26+2*TIER)*7+GROUP].astype(np.int32)&255)&(128>>SLOT))!=0
 deck=np.stack([pool[:,TIER==t].sum(1) for t in range(3)],axis=1)
 for slot in range(3):
  active=context[:,slot]==1
  if not active.any():continue
  r=50+2*slot;t=np.rint(context[active,slot+3]*3).astype(int)-1
  match=(x[active,r*7:r*7+5,None]==COST.T).all(1)&(x[active,(r+1)*7:(r+1)*7+5,None]==BONUS.T).all(1)&(x[active,(r+1)*7+6,None]==POINTS)&(t[:,None]==TIER)
  assert (match.sum(1)==1).all()
  selected=match.argmax(1);indices=np.flatnonzero(active);assert not pool[indices,selected].any();pool[indices,selected]=True
 mean=x.copy();prob=np.zeros((b,3),dtype=np.float64)
 for t in range(3):
  tierpool=pool&(TIER==t);n=tierpool.sum(1);p=np.divide(deck[:,t],n,out=np.zeros(b),where=n>0);prob[:,t]=p
  for g in range(5):
   mask=tierpool&(GROUP==g);bits=(mask*(128>>SLOT)).sum(1);signed=np.where(bits<128,bits,bits-256)
   mean[:,(25+2*t)*7+g]=mask.sum(1)*p;mean[:,(26+2*t)*7+g]=signed*p
  for slot in range(3):
   active=(context[:,slot]==1)&(np.rint(context[:,slot+3]*3)==t+1)
   if not active.any():continue
   r=50+2*slot;u=tierpool[active].astype(np.float64);den=n[active,None]
   mean[active,r*7:r*7+5]=u@COST/den
   mean[active,(r+1)*7:(r+1)*7+5]=u@BONUS/den
   mean[active,(r+1)*7+6]=u@POINTS/n[active]
 features=np.zeros((b,519),dtype=np.float32);features[:,:392]=mean*np.float32(.1);features[:,6]=mean[:,6]*np.float32(1/124)
 for t in range(3):features[:,(26+2*t)*7:(26+2*t)*7+5]=0
 features[:,392+(TIER*5+GROUP)*8+7-SLOT]=pool*prob[:,TIER];features[:,512:]=context
 return mean,features
if __name__=='__main__':
 import json
 rows=[json.loads(s) for s in (ROOT/'local/research/e85/moments.jsonl').open()]
 x=np.array([r['x'] for r in rows],dtype=np.float32);context=np.array([r['context'] for r in rows],dtype=np.float32)
 mean,features=batch(x,context)
 assert np.array_equal(mean,np.array([r['mean'] for r in rows],dtype=np.float32))
 assert np.array_equal(features,np.array([r['features'] for r in rows],dtype=np.float32))
 print(json.dumps(dict(rows=len(rows),exact_batched_rust_parity=True)))
