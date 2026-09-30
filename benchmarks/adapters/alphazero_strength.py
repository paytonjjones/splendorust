#!/usr/bin/env python3
"""Native AlphaZero policy, sampled observation input, canonical action output."""
import argparse
import contextlib
import json
import random
import sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--players',type=int,default=2)
    p.add_argument('--simulations',type=int,default=0)
    args=p.parse_args()
    sys.path.insert(0,str(args.root.resolve()))
    import numpy as np
    import torch
    from splendor import SplendorGame as game_module
    game_module.NUMBER_PLAYERS=args.players
    from splendor.NNet import NNetWrapper
    from splendor.SplendorLogic import (np_all_cards_1,np_all_cards_2,np_all_cards_3,
                                      np_all_nobles,np_different_gems_up_to_3)
    from splendor.SplendorLogicNumba import my_packbits
    from MCTS import MCTS
    from utils import dotdict
    game=game_module.SplendorGame()
    with contextlib.redirect_stdout(sys.stderr):
        net=NNetWrapper(game,dict(lr=None,dropout=0.,epochs=None,batch_size=None,nn_version=-1))
        checkpoint=net.load_checkpoint(str(args.root/'splendor'),f'pretrained_{args.players}players.pt')
    if not checkpoint: raise RuntimeError('checkpoint load failed')
    # Require the full checkpoint model. No partial architecture load is allowed.
    for name,value in checkpoint['state_dict'].items():
        assert torch.equal(net.nnet.state_dict()[name],value),name
    cpuct=checkpoint.get('cpuct')
    if isinstance(cpuct,list): cpuct=float(cpuct[0])
    config=dotdict(dict(numMCTSSims=args.simulations or checkpoint.get('numMCTSSims',100),
        fpu=checkpoint.get('fpu',0.),universes=checkpoint.get('universes',1),cpuct=cpuct,
        prob_fullMCTS=1.,forced_playouts=False,no_mem_optim=False))
    tree=MCTS(game,net,config)
    mapping={}; cards={}; nobles=[]
    initial_nobles=[]
    print(json.dumps({'ready':True,'config':dict(config),'checkpoint_keys':sorted(checkpoint),
                      'architecture_version':net.nnet.version,'inference':'upstream ONNX export, CPU'}),flush=True)
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request['op']=='data':
                cards=request['cards']; nobles=request['nobles']
                seen=set()
                for id,c in enumerate(cards):
                    for color,row in enumerate((np_all_cards_1,np_all_cards_2,np_all_cards_3)[c['tier']]):
                        for index,native in enumerate(row):
                            bonus=np.zeros(7,dtype=np.int8);bonus[c['bonus']]=1;bonus[6]=c['points']
                            if list(native[0,:5])==c['cost'] and np.array_equal(native[1],bonus):
                                mapping[id]=(color,index,native);seen.add((c['tier'],color,index))
                assert len(mapping)==len(seen)==90,'card data mismatch'
                assert sorted(tuple(n['cost']) for n in nobles)==sorted(tuple(n[:5]) for n in np_all_nobles),'noble data mismatch'
                response={'ok':True,'matched_cards':90,'matched_nobles':10}
            elif request['op']=='reset':
                seed=request['seed']; np.random.seed(seed%2**32);random.seed(seed);torch.manual_seed(seed)
                tree=MCTS(game,net,config);tree.rng=np.random.default_rng(seed)
                initial_nobles=[]
                response={'ok':True}
            elif request['op']=='choose':
                o=request['observation'];n=args.players
                if o['turns']>=62*n:
                    response={'unsupported':'native_turn_cap'}
                else:
                    assert o.get('sampled_hidden_world') is True
                    board=game.board
                    state=np.zeros(game.getBoardSize(),dtype=np.int8);board.copy_state(state,False)
                    board.bank[0,:6]=o['bank'];board.bank[0,6]=o['turns']
                    occupied=set()
                    for slot,id in enumerate(o['market']):
                        if id!=255:
                            board.cards_tiers[2*slot:2*slot+2]=mapping[id][2];occupied.add(id)
                    ids=set(o['nobles'])
                    for player in o['players']:ids.update(player['nobles'])
                    if not initial_nobles:initial_nobles=sorted(ids)
                    assert ids==set(initial_nobles)
                    for k,id in enumerate(initial_nobles):
                        data=np.array(nobles[id]['cost']+[0,3],dtype=np.int8)
                        if id in o['nobles']:board.nobles[k]=data
                        for i,player in enumerate(o['players']):
                            if id in player['nobles']:board.players_nobles[(n+1)*i+k]=data
                    for i,player in enumerate(o['players']):
                        board.players_gems[i,:6]=player['tokens']
                        board.players_cards[i,:5]=player['bonuses']
                        board.players_cards[i,6]=player['score']-3*len(player['nobles'])
                        occupied.update(player['owned'])
                        for slot,r in enumerate(player['reserved']):
                            if r['card']!=255:
                                board.players_reserved[6*i+2*slot:6*i+2*slot+2]=mapping[r['card']][2]
                                occupied.add(r['card'])
                    for tier,table in enumerate((np_all_cards_1,np_all_cards_2,np_all_cards_3)):
                        masks=np.zeros((5,len(table[0])),dtype=np.int8)
                        for id,c in enumerate(cards):
                            if c['tier']==tier and id not in occupied:
                                color,index,_=mapping[id];masks[color,index]=1
                        board.nb_deck_tiers[2*tier,:5]=masks.sum(axis=1)
                        board.nb_deck_tiers[2*tier+1,:5]=np.asarray([my_packbits(row) for row in masks],dtype=np.uint8).view(np.int8)
                        assert masks.sum()==o['remaining'][tier]
                    original=state.copy()
                    canonical=game.getCanonicalForm(state,o['current'])
                    with contextlib.redirect_stdout(sys.stderr):
                        probs=tree.getActionProb(canonical,temp=.5 if o['turns']+1<=6 else 0.,force_full_search=True)[0]
                    native=int(np.argmax(probs))
                    game.board.copy_state(original,False)
                    assert game.getValidMoves(original,o['current'])[native]
                    if native<12: action=[3,native,0,0,0,0,0]
                    elif native<24: action=[1,native-12,0,0,0,0,0]
                    elif native<27: action=[2,native-24,0,0,0,0,0]
                    elif native<30: action=[4,native-27,0,0,0,0,0]
                    elif native<55: action=[0]+list(map(int,np_different_gems_up_to_3[native-30,:5]))+[0]
                    elif native<60:
                        q=[0]*5;q[native-55]=2;action=[0]+q+[0]
                    else: action=None
                    response={'action':action,'native_action':native}
                    if action is None:response['unsupported']='native_pass' if native==80 else 'native_voluntary_return'
            else:raise ValueError('unknown operation')
        except Exception as e:
            response={'error':f'{type(e).__name__}: {e}'}
        print(json.dumps(response),flush=True)

if __name__=='__main__':main()
