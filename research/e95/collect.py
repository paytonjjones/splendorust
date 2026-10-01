"""Frozen external-teacher shard collection with public-only learner inputs."""
import json,sys,tempfile,os,time,hashlib,argparse,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'benchmarks/strength/native'));sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'research/e86'))
from upstream import Upstream,Tracker,PIN,SOURCE,stream,sha
from validate import RPC
from flywheel_model import DTYPE
from public_features import batch
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--master',type=int,required=True);ap.add_argument('--offset',type=int,default=0);ap.add_argument('--games',type=int,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=False);LOCAL=OUT;master=args.master;start=time.monotonic();WORKER=ROOT/'local/research/e92/frozen/native_policy_worker'
paths=[Path(__file__),ROOT/'benchmarks/strength/native/upstream.py',ROOT/'research/e86/public_features.py',WORKER,SOURCE/'splendor/pretrained_2players.pt']
plan=dict(schema='public-input-external-teacher-shard-v1',games=args.games,offset=args.offset,master=master,files={str(p):sha(p) for p in paths},upstream_revision=PIN,scope='Native privileged teacher labels; public-only learner inputs',teacher_value='Selected-action root Qsa mapped to credit')
assert not (OUT/'plan.json').exists();(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
rows=[];contexts=[];histories=[];invariance=0
with tempfile.TemporaryDirectory(prefix='external-teacher-pilot-') as tmp:
 os.chdir(tmp);u=Upstream(network=True);rpc=RPC([WORKER,ROOT/'research/e81/model/model.bin'])
 try:
  for game in range(args.offset,args.offset+args.games):
   setup=stream(master,'setup',game);state=u.setup(setup);initial=state.copy();tracker=Tracker(u,state);trees=[]
   for seat in range(2):u.reset_policy(stream(master,'policy',game,seat));trees.append(u.tree)
   current=0;game_rows=[];record=dict(game=game,setup=setup,initial_state=initial.astype(int).tolist(),actions=[],chance_seeds=[],state_sha256=[],public_observations=[],public_observation_sha256=[],actors=[],status='incomplete')
   for turn in range(125):
    rewards=u.rewards(state,current)
    if rewards is not None:
     winners=[i for i,v in enumerate(rewards) if v>0];credit=[1/len(winners) if i in winners else 0 for i in range(2)];record.update(status='complete',native_rewards=rewards,credits=credit);break
    observation=tracker.snapshot(state,current);opponent=observation['players'][1-current];ctx=np.zeros(7,dtype='<f4')
    for slot,r in enumerate(opponent['reserved'][:opponent['reserved_count']]):
     assert r['public'] or r['card']==255
     ctx[slot]=not r['public'];ctx[slot+3]=(r['tier']+1)/3;ctx[6]+=ctx[slot]/3
    sample_seed=stream(master,'encoding',game,turn);sample=rpc.call(op='sample',observation=observation,seed=sample_seed);x=np.asarray(sample['features'],dtype='<f4');assert x.shape==(392,) and np.isfinite(x).all()
    if turn<2:
     xs=[x]
     for repeat in range(1,8):xs.append(np.asarray(rpc.call(op='sample',observation=observation,seed=stream(master,'encoding-view',game,turn*8+repeat))['features'],dtype='<f4'))
     means,public=batch(np.array(xs),np.repeat(ctx[None,:],8,axis=0));assert np.array_equal(means,np.repeat(means[:1],8,axis=0)) and np.array_equal(public,np.repeat(public[:1],8,axis=0));invariance+=1
    legal=u.legal(state,current);canonical=u.game.getCanonicalForm(state,current).copy();u.tree=trees[current]
    probs,q,full=u.tree.getActionProb(canonical,temp=.5 if turn+1<=6 else 0.,force_full_search=True);assert full
    action=int(np.argmax(probs));assert action in legal;node=u.tree.nodes_data[u.game.stringRepresentation(canonical)];assert node[5][action]>0;selected_q=float(node[4][action]);assert np.isfinite(selected_q);teacher_credit=(selected_q+1)/2;assert 0<=teacher_credit<=1
    row=np.zeros((),dtype=DTYPE);row['setup']=setup;row['x']=x;row['mask'][legal]=1;row['policy'][action]=1;row['teacher']=teacher_credit;row['outcome']=np.nan;game_rows.append((row,ctx,current))
    record['actors'].append(current);record['public_observations'].append(observation);record['public_observation_sha256'].append(hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest())
    chance=stream(master,'chance',game,turn);child,new_current=u.apply(state,current,action,chance);tracker.update(state,child,current,action);state,current=child,new_current
    record['actions'].append(action);record['chance_seeds'].append(chance);record['state_sha256'].append(hashlib.sha256(state.tobytes()).hexdigest())
   assert record['status']=='complete','incomplete pilot is not usable data'
   for row,ctx,actor in game_rows:row['outcome']=record['credits'][actor];rows.append(row);contexts.append(ctx)
   histories.append(record);print(json.dumps(dict(completed_games=game-args.offset+1,rows=len(rows),seconds=time.monotonic()-start)),flush=True)
 finally:rpc.close()
 # Replay all histories and public model inputs, independently of teacher policy.
 v=Upstream();transitions=0
 for record in histories:
  state=v.setup(record['setup']);assert np.array_equal(state,np.array(record['initial_state'],dtype=np.int8));tracker=Tracker(v,state);current=0
  for turn,action in enumerate(record['actions']):
   assert v.rewards(state,current) is None and action in v.legal(state,current);observation=tracker.snapshot(state,current);assert observation==record['public_observations'][turn];assert hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest()==record['public_observation_sha256'][turn]
   child,new_current=v.apply(state,current,action,record['chance_seeds'][turn]);tracker.update(state,child,current,action);state,current=child,new_current;assert hashlib.sha256(state.tobytes()).hexdigest()==record['state_sha256'][turn];transitions+=1
  assert v.rewards(state,current)==record['native_rewards']
 a=np.array(rows,dtype=DTYPE);c=np.array(contexts,dtype='<f4');assert np.isfinite(a['x']).all() and np.isfinite(c).all() and np.all(a['policy'].sum(-1)==1) and np.all(a['policy']<=a['mask']);a.tofile(LOCAL/'data.bin');c.tofile(LOCAL/'data.context.bin')
 with (OUT/'histories.json.gz').open('wb') as raw:
  with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz:gz.write((json.dumps(dict(plan=plan,games=histories))+'\n').encode())
 result=dict(games=args.games,completed=len(histories),offset=args.offset,master=master,rows=len(a),public_encoding_invariance_checks=invariance,replay_transitions=transitions,data_sha256=sha(LOCAL/'data.bin'),context_sha256=sha(LOCAL/'data.context.bin'),histories_sha256=sha(OUT/'histories.json.gz'),teacher_config=dict(u.config),seconds=time.monotonic()-start,learner_inputs='Public observation sampling and public reservation metadata only; privileged teacher information appears only in labels',training_eligible=True,scope='Teacher corpus only; no model strength claim')
 assert all(sha(p)==h for p,h in plan['files'].items());(OUT/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
