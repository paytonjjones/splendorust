#!/usr/bin/env python3
"""Verify all card semantics before exporting native-board slot mappings."""
import json,subprocess,sys
from pathlib import Path
import numpy as np
root=Path('local/strength/external/alphazero').resolve();sys.path.insert(0,str(root))
from splendor.SplendorLogic import np_all_cards_1,np_all_cards_2,np_all_cards_3,np_different_gems_up_to_3
proc=subprocess.run(['target/release/examples/strength_worker'],input='{"op":"data"}\n',text=True,capture_output=True,check=True)
data=json.loads(proc.stdout)
slots=[];groups=[];seen=set()
for c in data['cards']:
    table=(np_all_cards_1,np_all_cards_2,np_all_cards_3)[c['tier']]
    candidates=[]
    for color,row in enumerate(table):
        for index,card in enumerate(row):
            bonus=np.zeros(7,dtype=np.int8);bonus[c['bonus']]=1;bonus[6]=c['points']
            if list(card[0,:5])==c['cost'] and np.array_equal(card[1],bonus): candidates.append((color,index))
    assert len(candidates)==1
    color,index=candidates[0];seen.add((c['tier'],color,index));slots.append(index);groups.append(color)
assert len(seen)==90
masks=[sum(1<<c for c in range(5) if row[c]) for row in np_different_gems_up_to_3]
assert len(set(masks))==25
text='// Verified semantic mappings to the MIT-licensed upstream network input.\n'
text+='pub const CARD_SLOT: [u8; 90] = '+str(slots)+';\n'
text+='pub const CARD_GROUP: [u8; 90] = '+str(groups)+';\n'
text+='pub const TAKE_MASKS: [u8; 25] = '+str(masks)+';\n'
Path('crates/splendor-agents/src/transfer_data.rs').write_text(text)
Path('research/e30/mapping.json').write_text(json.dumps(dict(cards=data['cards'],nobles=data['nobles'],card_slots=slots,card_groups=groups,take_masks=masks),indent=2)+'\n')
