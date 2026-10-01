"""Public first moments, matched to Rust belief::moments."""
import csv,re
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
s=(ROOT/'crates/splendor-agents/src/transfer_data.rs').read_text()
def table(name):
 return list(map(int,re.search(r'pub const '+name+r'[^=]*=\s*\[([^]]+)\]',s).group(1).replace('\n','').split(',')[:-1]))
GROUP,SLOT=table('CARD_GROUP'),table('CARD_SLOT')
COLORS=['white','blue','green','red','black']
CARDS=list(csv.DictReader((ROOT/'data/cards.csv').open()))
def moments(x,context):
 x=np.asarray(x,dtype=np.float32);context=np.asarray(context,dtype=np.float32)
 pool=set();deck=[0]*3;unknown={}
 for i,c in enumerate(CARDS):
  t=int(c['tier'])-1;bits=int(x[(26+2*t)*7+GROUP[i]])&255
  if bits&(128>>SLOT[i]):pool.add(i);deck[t]+=1
 for slot in range(3):
  if not context[slot]:continue
  t=int(round(float(context[slot+3])*3))-1;r=50+2*slot
  ids=[i for i,c in enumerate(CARDS) if int(c['tier'])-1==t and all(x[r*7+j]==int(c[col]) for j,col in enumerate(COLORS)) and all(x[(r+1)*7+j]==int(col==c['bonus']) for j,col in enumerate(COLORS)) and x[(r+1)*7+6]==int(c['points'])]
  assert len(ids)==1 and ids[0] not in pool
  pool.add(ids[0]);unknown[slot]=t
 mean=x.copy();p=[0.]*3
 for t in range(3):
  ids=[i for i in pool if int(CARDS[i]['tier'])-1==t];n=len(ids);p[t]=deck[t]/n if n else 0.
  for g in range(5):
   members=[i for i in ids if GROUP[i]==g];mask=sum(128>>SLOT[i] for i in members)
   mean[(25+2*t)*7+g]=len(members)*p[t]
   mean[(26+2*t)*7+g]=(mask if mask<128 else mask-256)*p[t]
  for slot,tier in unknown.items():
   if tier!=t:continue
   r=50+2*slot
   for j,col in enumerate(COLORS):
    mean[r*7+j]=sum(int(CARDS[i][col]) for i in ids)/n
    mean[(r+1)*7+j]=sum(CARDS[i]['bonus']==col for i in ids)/n
   mean[(r+1)*7+6]=sum(int(CARDS[i]['points']) for i in ids)/n
 features=np.zeros(519,dtype=np.float32);features[:392]=mean*np.float32(.1);features[6]=mean[6]*np.float32(1/124)
 for t in range(3):features[(26+2*t)*7:(26+2*t)*7+5]=0
 for i in pool:
  t=int(CARDS[i]['tier'])-1;features[392+(t*5+GROUP[i])*8+7-SLOT[i]]=p[t]
 features[512:]=context
 return mean,features
if __name__=='__main__':
 import json,sys
 maximum=[0.,0.];rows=0;blind=0;observations={}
 for line in Path(sys.argv[1]).open():
  r=json.loads(line);mean,features=moments(r['x'],r['context']);rows+=1;blind+=r['context'][6]>0
  for j,(actual,key) in enumerate([(mean,'mean'),(features,'features')]):maximum[j]=max(maximum[j],float(np.max(np.abs(actual-np.asarray(r[key],dtype=np.float32)))))
  assert np.array_equal(mean,np.asarray(r['mean'],dtype=np.float32))
  assert np.array_equal(features,np.asarray(r['features'],dtype=np.float32))
  key=(r['stress'],r['seed'],r['turn']);old=observations.setdefault(key,(mean,features))
  assert np.array_equal(old[0],mean) and np.array_equal(old[1],features)
 result=dict(rows=rows,observations=len(observations),blind_rows=blind,max_abs_error=maximum,exact_python_rust_parity=True,sampled_world_invariance=True)
 print(json.dumps(result,indent=2))
