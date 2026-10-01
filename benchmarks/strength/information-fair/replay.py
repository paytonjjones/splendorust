#!/usr/bin/env python3
"""Check every saved native action, chance draw, public input and reward."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
from boundary import ROOT, Upstream, Tracker, sha, stream, digest, blind_input, privileged_input, RPC
from upstream import PIN

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    meta,*rows=map(json.loads,a.input.read_text().splitlines())
    assert meta['upstream_revision']==PIN
    assert len(rows)==meta['games']
    u=Upstream();count=0;decisions=0
    rpc=RPC([ROOT/'target/release/examples/native_policy_worker',ROOT/'research/e81/model/model.bin'])
    arm=meta['information_arm']
    hidden_positions=collections.Counter();hidden_slots=collections.Counter();changed_blind_inputs=0
    start_index=2*meta.get('offset_block',0)
    for index,row in enumerate(rows,start_index):
        assert row['index']==index
        assert row['rotation']==index%2 and row['block']==index//2
        assert row['setup_seed']==stream(meta['master'],'setup',row['block'])
        expected=u.setup(row['setup_seed'])
        state=u.np.asarray(row['initial_state'],dtype=u.np.int8)
        assert u.np.array_equal(state,expected)
        if index%2==1:
            assert rows[index-start_index-1]['initial_state']==row['initial_state']
        assert row['seats']==(['champion','alphazero'] if row['rotation']==0 else ['alphazero','champion'])
        assert len(row['actions'])==len(row['chance_seeds'])==len(row['state_sha256'])==len(row['policy_observation_sha256'])==len(row['alpha_input_sha256'])==len(row['alpha_public_sha256'])
        t=Tracker(u,state);seat=0
        for turn,(action,chance,state_digest,observation_digest) in enumerate(zip(row['actions'],row['chance_seeds'],row['state_sha256'],row['policy_observation_sha256'])):
            assert u.rewards(state,seat) is None
            assert action in u.legal(state,seat)
            assert chance==stream(meta['master'],'chance',row['block'],turn)
            actor=row['seats'][seat]
            public=t.snapshot(state,seat)
            n=sum(not r['public'] for r in public['players'][1-seat]['reserved'][:public['players'][1-seat]['reserved_count']])
            hidden_positions[actor]+=bool(n);hidden_slots[actor]+=n
            if actor=='champion':
                observation=t.snapshot(state,seat)
                payload=privileged_input(t,state,seat) if arm=='privileged-sr' else observation
                assert observation_digest==digest(payload)
                assert row['alpha_input_sha256'][turn] is None and row['alpha_public_sha256'][turn] is None
                assert observation['players'][1-seat]['reserved'][:observation['players'][1-seat]['reserved_count']] == [
                    r if r['public'] else r|{'card':255}
                    for r in observation['players'][1-seat]['reserved'][:observation['players'][1-seat]['reserved_count']]]
            else:
                assert observation_digest is None
                observation=t.snapshot(state,seat)
                assert row['alpha_public_sha256'][turn]==digest(observation)
                if arm=='blind-alpha':
                    board=blind_input(rpc,observation,stream(meta['master'],'information',row['block'],turn),u.np)
                else:
                    board=u.game.getCanonicalForm(state,seat).copy()
                assert row['alpha_input_sha256'][turn]==hashlib.sha256(board.tobytes()).hexdigest()
                assert u.legal(board,0)==u.legal(state,seat)
                changed_blind_inputs+=int(arm=='blind-alpha' and not u.np.array_equal(board,u.game.getCanonicalForm(state,seat)))
            child,next_seat=u.apply(state,seat,action,chance)
            t.update(state,child,seat,action);state,seat=child,next_seat
            assert hashlib.sha256(state.tobytes()).hexdigest()==state_digest
            decisions+=1
        assert row['turns']==len(row['actions'])==row['decisions']
        assert row['scores']==[u.game.getScore(state,i) for i in range(2)]
        reward=u.rewards(state,seat)
        if row['status']=='complete':
            assert reward is not None
            assert row['native_rewards']==reward
            winners=[i for i,r in enumerate(reward) if r>0]
            assert row['rewards']==[1/len(winners) if i in winners else 0 for i in range(2)]
        else:assert reward is None and row['rewards'] is None and row['native_rewards'] is None
        count+=1
    rpc.close()
    a.output.write_text(json.dumps(dict(information_arm=arm,opponent_blind_positions=dict(hidden_positions),opponent_blind_slots=dict(hidden_slots),changed_blind_inputs=changed_blind_inputs,checked_games=count,checked_transitions=decisions,raw_sha256=sha(a.input),
        script_sha256=sha(__file__),upstream_revision=PIN,
        scope='Every native legal action, seeded chance draw, state digest, public policy input digest, score and signed terminal reward; exact paired setups and all information inputs including blind reconstruction and privileged partition. No policy rerun or independent proof of all upstream rules.'),indent=2)+'\n')
    print(count,decisions,'native histories verified')
if __name__=='__main__':main()
