#!/usr/bin/env python3
"""Check every saved native action, chance draw, public input and reward."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from upstream import ROOT, PIN, Upstream, Tracker, sha, stream, DEFAULT_STRENGTH_BINARY

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--strength-binary',type=Path);a=p.parse_args()
    meta,*rows=map(json.loads,a.input.read_text().splitlines())
    assert meta['upstream_revision']==PIN
    assert len(rows)==meta['games']
    strength_binary=Path(a.strength_binary or meta.get('strength_binary_path') or DEFAULT_STRENGTH_BINARY).resolve(strict=True)
    expected_strength_sha=meta.get('strength_binary_sha256')
    if expected_strength_sha and sha(strength_binary)!=expected_strength_sha:
        raise ValueError('strength binary SHA256 differs from run metadata')
    u=Upstream(strength_binary=strength_binary);count=0;decisions=0
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
        assert len(row['actions'])==len(row['chance_seeds'])==len(row['state_sha256'])==len(row['policy_observation_sha256'])
        t=Tracker(u,state);seat=0
        for turn,(action,chance,digest,observation_digest) in enumerate(zip(row['actions'],row['chance_seeds'],row['state_sha256'],row['policy_observation_sha256'])):
            assert u.rewards(state,seat) is None
            assert action in u.legal(state,seat)
            assert chance==stream(meta['master'],'chance',row['block'],turn)
            if row['seats'][seat]=='champion':
                observation=t.snapshot(state,seat)
                assert observation_digest==hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest()
                assert observation['players'][1-seat]['reserved'][:observation['players'][1-seat]['reserved_count']] == [
                    r if r['public'] else r|{'card':255}
                    for r in observation['players'][1-seat]['reserved'][:observation['players'][1-seat]['reserved_count']]]
            else:assert observation_digest is None
            child,next_seat=u.apply(state,seat,action,chance)
            t.update(state,child,seat,action);state,seat=child,next_seat
            assert hashlib.sha256(state.tobytes()).hexdigest()==digest
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
    a.output.write_text(json.dumps(dict(checked_games=count,checked_transitions=decisions,raw_sha256=sha(a.input),
        script_sha256=sha(__file__),upstream_revision=PIN,
        scope='Every native legal action, seeded chance draw, state digest, public policy input digest, score and signed terminal reward; exact paired setups. No policy rerun or independent proof of all upstream rules.'),indent=2)+'\n')
    print(count,decisions,'native histories verified')
if __name__=='__main__':main()
