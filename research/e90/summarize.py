import json,collections,itertools,math,statistics,hashlib
from pathlib import Path
out=Path(__file__).parent;r=json.loads((out/'raw.json').read_text());s={}
def mode(v):
 c=collections.Counter(v);return min(c,key=lambda a:(-c[a],a))
for budget in [128,800]:
 for group in ['all','blind','known']:
  observations=[o for o in r['observations'] if group=='all' or (o['context'][-1]>0)==(group=='blind')];pairs=[];split=[];entropy=[];values=[];prior=[];majority=[];singles=[];unique=[]
  for o in observations:
   searches=[x for x in o['searches'] if x['iterations']==budget];actions=[x['chosen_index'] for x in searches];counts=collections.Counter(actions);pairs.extend(a==b for a,b in itertools.combinations(actions,2));split.append(mode(actions[:4])==mode(actions[4:]));entropy.append(-sum((n/8)*math.log(n/8) for n in counts.values()));values.append(statistics.pstdev(x['value'] for x in searches));prior.append(sum(a==o['root_argmax'] for a in actions)/8);majority.append(max(counts.values())/8);unique.append(len(counts));singles.append(actions[0]==mode(actions[1:]))
  s[f'{budget}/{group}']=dict(observations=len(observations),pairwise_action_agreement=statistics.mean(pairs),four_vs_four_consensus_agreement=statistics.mean(split),mean_action_entropy_nats=statistics.mean(entropy),mean_value_sd=statistics.mean(values),prior_action_credit_under_empirical_search_actions=statistics.mean(prior),mean_largest_vote_fraction=statistics.mean(majority),mean_distinct_actions=statistics.mean(unique),first_action_agrees_remaining_seven_mode=statistics.mean(singles))
s.update(positions=r['positions'],seconds=r['seconds'],all_native_encodings_invariant=all(o['native_encoding_invariant'] for o in r['observations']),raw_sha256=hashlib.sha256((out/'raw.json').read_bytes()).hexdigest(),scope=r['scope'],tie_rule='smallest native action index for descriptive consensus; playing teacher selection not defined here',next_step='test consensus teacher strength before training; low action agreement does not prove causation')
(out/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))
