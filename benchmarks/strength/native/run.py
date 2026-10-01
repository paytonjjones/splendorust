#!/usr/bin/env python3
"""Unchanged AlphaZero, its native referee, observation-only SplendoRust."""
import argparse
import contextlib
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from upstream import ROOT, SOURCE, PIN, Upstream, Tracker, sha, stream
from validate import RPC

PROFILE='alphazero-native-32a27ac-v1'

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,required=True)
    p.add_argument('--master',type=int,required=True);p.add_argument('--offset-block',type=int,default=0)
    p.add_argument('--search',choices=['puct','gumbel'],default='puct');p.add_argument('--iterations',type=int,default=128);p.add_argument('--depth',type=int,default=16)
    p.add_argument('--model',type=Path,default=ROOT/'research/e56/model/model.bin')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.games<=0 or a.games%2 or a.offset_block<0:p.error('require full two-seat blocks')
    if a.output.exists():p.error('output already exists')
    a.output=a.output.resolve();a.model=a.model.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
    command=list(__import__('sys').argv)
    startup=time.perf_counter()
    # Isolate upstream temporary ONNX filenames; upstream source is untouched.
    with tempfile.TemporaryDirectory(prefix='native-alpha-') as temporary:
        os.chdir(temporary)
        u=Upstream(network=True)
        rpc=RPC([ROOT/'target/release/examples/native_policy_worker',a.model])
        metadata=dict(schema_version=1,engine='alphazero_native',ruleset=PROFILE,planning_profile=PROFILE,
            observation_profile='native-public-history-v1',players=2,games=a.games,candidate='champion',external='alphazero',
            master=a.master,offset_block=a.offset_block,iterations=a.iterations,depth=a.depth,world_pool=3,search=a.search,search_profile='native-public-gumbel-v1' if a.search=='gumbel' else 'native-public-puct-v1',gumbel_config=dict(max_considered=16,cvisit=50,cscale=.1,root_noise=0) if a.search=='gumbel' else None,
            cpuct=.4,fpu_reduction=.02965,uniform_prior=0,external_config=dict(u.config),
            upstream_revision=PIN,upstream_checkpoint_sha256=sha(SOURCE/'splendor/pretrained_2players.pt'),
            model_sha256=sha(a.model),model_path=str(a.model),policy_binary_sha256=sha(ROOT/'target/release/examples/native_policy_worker'),
            source_id=u.data['source_id'],engine_version=u.data['engine'],
            revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
            source_sha256={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__),Path(__file__).with_name('upstream.py'),ROOT/'crates/splendor-agents/src/environment.rs',ROOT/'crates/splendor-agents/src/native_environment.rs',ROOT/'crates/splendor-agents/src/neural_search.rs',ROOT/'crates/splendor-arena/examples/native_policy_worker.rs',ROOT/'crates/splendor-arena/examples/native_wire/mod.rs']},
            reproduction_command=command,host=platform.platform(),startup_seconds=time.perf_counter()-startup,
            streams='SHA256 native-v1:{master}:{label}:{block}:{identity}, first 8 bytes little-endian; setup/referee use low32, policy uses64',
            alpha_information='Unchanged upstream true unordered deck membership and all private reserved identities. SplendoRust samples private information from the actor public observation only.',
            limits='Native rules and native score-cap wins, not canonical rank. Fixed simulations are not equal compute.')
        with a.output.open('x') as out:
            out.write(json.dumps(metadata)+'\n');out.flush()
            try:
                for local_block in range(a.games//2):
                    block=a.offset_block+local_block
                    setup_seed=stream(a.master,'setup',block)
                    initial=u.setup(setup_seed)
                    for rotation in range(2):
                        state=initial.copy();seat=0;t=Tracker(u,state)
                        splendor_seed=stream(a.master,'policy',block,0)
                        alpha_seed=stream(a.master,'policy',block,1)
                        rpc.call(op='reset',seed=splendor_seed,iterations=a.iterations,depth=a.depth,search=a.search)
                        u.reset_policy(alpha_seed)
                        seats=['champion','alphazero'] if rotation==0 else ['alphazero','champion']
                        record=dict(index=2*block+rotation,block=block,rotation=rotation,setup_seed=setup_seed,seats=seats,
                            status='decision_limit',reason=None,rewards=None,native_rewards=None,
                            initial_state=initial.astype(int).tolist(),actions=[],chance_seeds=[],state_sha256=[],policy_observation_sha256=[],
                            policy_seconds=[0.,0.],simulations=0,inferences=0,policy_seeds=[splendor_seed,alpha_seed])
                        started=time.perf_counter()
                        try:
                            for turn in range(125):
                                reward=u.rewards(state,seat)
                                if reward is not None:
                                    winners=[i for i,r in enumerate(reward) if r>0]
                                    record.update(status='complete',native_rewards=reward,
                                        rewards=[1/len(winners) if i in winners else 0 for i in range(2)],
                                        termination='native_turn_cap' if turn>=124 and max(u.game.getScore(state,i) for i in range(2))<15 else 'native_score')
                                    break
                                legal=u.legal(state,seat)
                                tick=time.perf_counter()
                                if seats[seat]=='champion':
                                    observation=t.snapshot(state,seat)
                                    result=rpc.call(op='choose',observation=observation,legal=legal)
                                    action=result['action'];record['simulations']+=result['simulations'];record['inferences']+=result['inferences']
                                    record['policy_observation_sha256'].append(__import__('hashlib').sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest())
                                else:
                                    action=u.choose(state,seat)
                                    record['policy_observation_sha256'].append(None)
                                record['policy_seconds'][seat]+=time.perf_counter()-tick
                                if action not in legal:raise ValueError(('illegal decision',action,legal))
                                chance_seed=stream(a.master,'chance',block,turn)
                                child,new_seat=u.apply(state,seat,action,chance_seed)
                                t.update(state,child,seat,action)
                                state,seat=child,new_seat
                                record['actions'].append(action);record['chance_seeds'].append(chance_seed)
                                record['state_sha256'].append(__import__('hashlib').sha256(state.tobytes()).hexdigest())
                        except Exception as e:
                            record.update(status='invalid',reason=f'{type(e).__name__}: {e}')
                        record.update(scores=[u.game.getScore(state,i) for i in range(2)],turns=int(state[0,6].astype(u.np.uint8)),
                            decisions=len(record['actions']),elapsed_seconds=time.perf_counter()-started)
                        out.write(json.dumps(record)+'\n');out.flush()
                        print(f'{record["index"]} {record["status"]} {record["scores"]}',flush=True)
                        if record['status']!='complete':raise RuntimeError('incomplete native game retained; investigate before continuing')
            finally:rpc.close()
if __name__=='__main__':main()
