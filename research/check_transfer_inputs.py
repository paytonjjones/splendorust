#!/usr/bin/env python3
"""Compare Rust information-set encoding with upstream native board fields."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,str(Path('local/strength/external/alphazero').resolve()))
from splendor import SplendorGame as gm
gm.NUMBER_PLAYERS=2
game=gm.SplendorGame()
from splendor.SplendorLogic import np_all_cards_1,np_all_cards_2,np_all_cards_3
from splendor.SplendorLogicNumba import my_packbits
mapping=json.loads(Path('research/e30/mapping.json').read_text());cards=mapping['cards'];nobles=mapping['nobles']
tables=(np_all_cards_1,np_all_cards_2,np_all_cards_3)
native=[tables[c['tier']][group][slot] for c,group,slot in zip(cards,mapping['card_groups'],mapping['card_slots'])]
rows=[json.loads(line) for line in Path('research/e30/inputs.jsonl').read_text().splitlines()]
for row in rows:
    o=row['observation'];state=np.zeros((56,7),dtype=np.int8);b=game.board;b.copy_state(state,False)
    b.bank[0,:6]=o['bank'];b.bank[0,6]=o['turns'];occupied=set()
    for slot,id in enumerate(o['market']):
        if id!=255:b.cards_tiers[2*slot:2*slot+2]=native[id];occupied.add(id)
    ids=sorted(set(o['nobles'])|{id for p in o['players'] for id in p['nobles']})
    for k,id in enumerate(ids):
        data=np.array(nobles[id]['cost']+[0,3],dtype=np.int8)
        if id in o['nobles']:b.nobles[k]=data
        for i,p in enumerate(o['players']):
            if id in p['nobles']:b.players_nobles[3*i+k]=data
    for i,p in enumerate(o['players']):
        b.players_gems[i,:6]=p['tokens'];b.players_cards[i,:5]=p['bonuses'];b.players_cards[i,6]=p['score']-3*len(p['nobles']);occupied.update(p['owned'])
        for slot,r in enumerate(p['reserved']):
            if r['card']!=255:b.players_reserved[6*i+2*slot:6*i+2*slot+2]=native[r['card']];occupied.add(r['card'])
    for tier,table in enumerate(tables):
        masks=np.zeros((5,len(table[0])),dtype=np.int8)
        for id,c in enumerate(cards):
            if c['tier']==tier and id not in occupied:masks[mapping['card_groups'][id],mapping['card_slots'][id]]=1
        b.nb_deck_tiers[2*tier,:5]=masks.sum(axis=1)
        b.nb_deck_tiers[2*tier+1,:5]=np.asarray([my_packbits(m) for m in masks],dtype=np.uint8).view(np.int8)
    expected=game.getCanonicalForm(state,o['current']).astype(np.float32).reshape(-1)
    np.testing.assert_array_equal(row['x'],expected)
# Independent upstream outputs for the exact verified encodings.
checkpoint=Path('local/strength/external/alphazero/splendor/pretrained_2players.pt')
p=torch.load(checkpoint,map_location='cpu',weights_only=False);model=p['full_model'].cpu().eval();model.load_state_dict(p['state_dict'],strict=True)
x=torch.tensor(np.array([r['x'] for r in rows],dtype=np.float32)).reshape(-1,56,7)
with torch.no_grad():
    h=model.trunk(model.first_layer(x));logits=model.output_layers_PI(h);v=model.output_layers_V(h).tanh()
Path('research/e30/real-parity.json').write_text(json.dumps(dict(x=x.reshape(-1,392).tolist(),logits=logits.tolist(),values=v.tolist())))
Path('research/e30/input-check.json').write_text(json.dumps(dict(positions=len(rows),exact_upstream_encoding=True,opponent_blind_reservations_sampled=True,inputs_sha256=hashlib.sha256(Path('research/e30/inputs.jsonl').read_bytes()).hexdigest()),indent=2)+'\n')
