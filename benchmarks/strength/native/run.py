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
from upstream import ROOT, SOURCE, PIN, Upstream, Tracker, sha, stream, DEFAULT_STRENGTH_BINARY
from validate import RPC
from campaign_context import campaign_metadata

PROFILE='alphazero-native-32a27ac-v1'
DEFAULT_POLICY_BINARY=ROOT/'target/release/examples/native_policy_worker'

def apply_campaign_metadata(metadata,a,model,policy_binary,strength_binary,external_config):
    metadata.update(campaign_metadata(a.campaign_context,a,ROOT,model,policy_binary,strength_binary,external_config))
    return metadata

def validate_settings(iterations,depth,world_pool,gumbel_max_considered,chance_universes=0):
    if not 0<=iterations<=0xffffffff:raise ValueError('iterations must be in 0..=4294967295')
    if not 1<=depth<=124:raise ValueError('depth must be in 1..=124')
    if not 0<=world_pool<=64:raise ValueError('world-pool must be in 0..=64')
    if not 1<=gumbel_max_considered<=81:raise ValueError('gumbel-max-considered must be in 1..=81')
    if not 0<=chance_universes<=64:raise ValueError('chance-universes must be in 0..=64')

def validate_accepted_settings(expected,accepted):
    if accepted is None:
        if (expected['world_pool'],expected['gumbel_max_considered'],expected['chance_universes'],
                expected['dynamic_fpu'])!=(3,16,0,False):
            raise RuntimeError('worker does not report accepted search settings')
        return
    defaults={'chance_universes':0,'dynamic_fpu':False}
    if any(accepted.get(key)!=value for key,value in expected.items()
           if not (key in defaults and value==defaults[key] and key not in accepted)):
        raise RuntimeError(f'worker search settings differ: requested={expected}, accepted={accepted}')

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,required=True)
    p.add_argument('--master',type=int,required=True);p.add_argument('--offset-block',type=int,default=0)
    p.add_argument('--campaign-games',type=int,default=None)
    p.add_argument('--search',choices=['puct','gumbel'],default='puct');p.add_argument('--iterations',type=int,default=128);p.add_argument('--depth',type=int,default=16)
    p.add_argument('--world-pool',type=int,default=3);p.add_argument('--gumbel-max-considered',type=int,default=16)
    p.add_argument('--chance-universes',type=int,default=0)
    p.add_argument('--dynamic-fpu',action='store_true')
    p.add_argument('--root-only',action='store_true');p.add_argument('--model',type=Path,default=ROOT/'research/e56/model/model.bin')
    p.add_argument('--policy-binary',type=Path,default=DEFAULT_POLICY_BINARY)
    p.add_argument('--strength-binary',type=Path,default=DEFAULT_STRENGTH_BINARY)
    p.add_argument('--campaign-context',type=Path,default=None)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.games<=0 or a.games%2 or a.offset_block<0:p.error('require full two-seat blocks')
    if a.campaign_games is not None and (a.campaign_games<=0 or a.campaign_games%2 or
            a.offset_block+a.games//2>a.campaign_games//2):p.error('shard range exceeds campaign game count')
    if a.campaign_context is not None and a.campaign_games is None:p.error('campaign context requires --campaign-games')
    try:validate_settings(a.iterations,a.depth,a.world_pool,a.gumbel_max_considered,a.chance_universes)
    except ValueError as error:p.error(str(error))
    if a.output.exists():p.error('output already exists')
    a.output=a.output.resolve();a.model=a.model.resolve(strict=True);a.policy_binary=a.policy_binary.resolve(strict=True);a.strength_binary=a.strength_binary.resolve(strict=True);a.output.parent.mkdir(parents=True,exist_ok=True)
    if not a.policy_binary.is_file() or not os.access(a.policy_binary,os.X_OK):p.error('policy binary must be an executable file')
    if not a.strength_binary.is_file() or not os.access(a.strength_binary,os.X_OK):p.error('strength binary must be an executable file')
    command=list(__import__('sys').argv)
    startup=time.perf_counter()
    # Isolate upstream temporary ONNX filenames; upstream source is untouched.
    with tempfile.TemporaryDirectory(prefix='native-alpha-') as temporary:
        os.chdir(temporary)
        u=Upstream(network=True,strength_binary=a.strength_binary)
        rpc=RPC([a.policy_binary,a.model])
        metadata=dict(schema_version=1,engine='alphazero_native',ruleset=PROFILE,planning_profile=PROFILE,
            observation_profile='native-public-history-v1',players=2,games=a.games,candidate='champion',external='alphazero',
            master=a.master,offset_block=a.offset_block,iterations=a.iterations,depth=a.depth,world_pool=a.world_pool,chance_universes=a.chance_universes,dynamic_fpu=a.dynamic_fpu,root_only=a.root_only,search=a.search,search_profile='native-public-gumbel-v1' if a.search=='gumbel' else 'native-public-puct-v1',gumbel_max_considered=a.gumbel_max_considered if a.search=='gumbel' else None,gumbel_config=dict(max_considered=a.gumbel_max_considered,cvisit=50,cscale=.1,root_noise=0) if a.search=='gumbel' else None,
            cpuct=.4,fpu_reduction=.02965,uniform_prior=0,external_config=dict(u.config),
            upstream_revision=PIN,upstream_checkpoint_sha256=sha(SOURCE/'splendor/pretrained_2players.pt'),
            model_sha256=sha(a.model),model_path=str(a.model),policy_binary_path=str(a.policy_binary),policy_binary_sha256=sha(a.policy_binary),
            strength_binary_path=str(u.strength_binary),strength_binary_sha256=u.strength_binary_sha256,
            source_id=u.data['source_id'],engine_version=u.data['engine'],
            revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
            source_sha256={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__),Path(__file__).with_name('upstream.py'),Path(__file__).with_name('schedule.py'),ROOT/'crates/splendor-agents/src/environment.rs',ROOT/'crates/splendor-agents/src/native_environment.rs',ROOT/'crates/splendor-agents/src/neural_search.rs',ROOT/'crates/splendor-arena/examples/native_policy_worker.rs',ROOT/'crates/splendor-arena/examples/native_wire/mod.rs']},
            reproduction_command=command,host=platform.platform(),startup_seconds=time.perf_counter()-startup,
            streams='SHA256 native-v1:{master}:{label}:{block}:{identity}, first 8 bytes little-endian; setup/referee use low32, policy uses64',
            alpha_information='Unchanged upstream true unordered deck membership and all private reserved identities. SplendoRust samples private information from the actor public observation only.',
            limits='Native rules and native score-cap wins, not canonical rank. Fixed simulations are not equal compute.')
        apply_campaign_metadata(metadata,a,a.model,a.policy_binary,a.strength_binary,u.config)
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
                        reset=rpc.call(op='reset',seed=splendor_seed,iterations=a.iterations,depth=a.depth,world_pool=a.world_pool,gumbel_max_considered=a.gumbel_max_considered,chance_universes=a.chance_universes,dynamic_fpu=a.dynamic_fpu,search=a.search,root_only=a.root_only)
                        expected=dict(iterations=a.iterations,depth=a.depth,world_pool=a.world_pool,gumbel_max_considered=a.gumbel_max_considered,chance_universes=a.chance_universes,dynamic_fpu=a.dynamic_fpu,search=a.search,root_only=a.root_only)
                        accepted=reset.get('settings')
                        validate_accepted_settings(expected,accepted)
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
