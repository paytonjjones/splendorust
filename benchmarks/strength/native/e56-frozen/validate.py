#!/usr/bin/env python3
"""Differential states/branches against unchanged pinned AlphaZero rules."""
import argparse
import collections
import hashlib
import json
import random
import subprocess
from pathlib import Path
from upstream import ROOT, Upstream, Tracker, sha, stream

class RPC:
    def __init__(self, command):
        self.p = subprocess.Popen(list(map(str, command)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    def call(self, **payload):
        self.p.stdin.write(json.dumps(payload)+'\n'); self.p.stdin.flush()
        result = json.loads(self.p.stdout.readline())
        if 'error' in result: raise RuntimeError(result['error'])
        return result
    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=10); self.p.stdout.close()
        assert self.p.returncode == 0

def assert_result(u, tracker, state, current, result):
    assert result['legal'] == u.legal(state, current), ('legal', result['legal'], u.legal(state,current))
    canonical = u.game.getCanonicalForm(state, current).copy().astype(float).flatten().tolist()
    assert result['features'] == canonical, ('features',[(i,a,b) for i,(a,b) in enumerate(zip(result['features'],canonical)) if a!=b])
    for viewer in range(2):
        assert result['observations'][viewer] == tracker.snapshot(state, current, viewer=viewer), 'public snapshot'
    native = u.rewards(state, current)
    assert (native is None) == (result['rewards'] is None), ('terminal',native,result['rewards'])
    if native is not None:
        assert all(abs(a-b)<1e-7 for a,b in zip(native,result['rewards'])), ('rewards',native,result['rewards'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--games',type=int,default=100);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    u=Upstream();rpc=RPC([ROOT/'target/release/examples/native_rules_probe'])
    rng=random.Random(4200000000);actions=collections.Counter();positions=branches=terminals=0
    examples={}
    try:
        for game in range(a.games):
            state=u.setup(stream(4200000000,'setup',game));seat=0;t=Tracker(u,state)
            for turn in range(125):
                fixture=t.fixture(state,seat)
                result=rpc.call(**fixture)
                assert_result(u,t,state,seat,result);positions+=1
                if u.rewards(state,seat) is not None:
                    terminals+=1;break
                legal=u.legal(state,seat)
                # Every action at every sampled position, not only selected moves.
                for action in legal:
                    chance=stream(4200000000,'branch',game,turn)%(2**31-1)+1
                    import copy
                    child_tracker=copy.copy(t)
                    child_tracker.owned=copy.deepcopy(t.owned)
                    child_tracker.reservations=copy.deepcopy(t.reservations)
                    child,new_seat=u.apply(state,seat,action,chance,deterministic=True)
                    child_tracker.update(state,child,seat,action)
                    check=rpc.call(**fixture,action=action,chance_seed=chance)
                    assert_result(u,child_tracker,child,new_seat,check)
                    actions[action]+=1;branches+=1
                    examples.setdefault(str(action),dict(**fixture,action=action,chance_seed=chance))
                # Mix buy-first trajectories with random, return and pass coverage.
                buys=[x for x in legal if x<12 or 27<=x<30]
                action=rng.choice(buys if buys and game%3 else legal)
                chance=stream(4200000000,'trajectory',game,turn)%(2**31-1)+1
                child,new_seat=u.apply(state,seat,action,chance,deterministic=True)
                t.update(state,child,seat,action);state,seat=child,new_seat
    finally:rpc.close()
    missing=sorted(set(range(81))-set(actions))
    if missing:raise AssertionError(('uncovered native action encodings',missing))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(profile='alphazero-native-32a27ac-v1',upstream_revision=u.data.get('revision',__import__('upstream').PIN),games=a.games,
        positions=positions,branch_successors=branches,terminal_games=terminals,action_counts=dict(sorted(actions.items())),
        probe_sha256=sha(ROOT/'target/release/examples/native_rules_probe'),examples=examples),indent=2)+'\n')
    print(positions,branches,terminals)
if __name__=='__main__':main()
