#!/usr/bin/env python3
"""Load the fixed saved model unchanged; verify its contract and report failure."""
import argparse,hashlib,json,pickle,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
sys.path.insert(0,str(args.root/'Convenient Solver Stuff'))
import torch
from NeuralNet4 import NeuralNet4
results=[]
for path in sorted((args.root/'Saved Weights').iterdir()):
    weights=pickle.load(path.open('rb'))
    model=NeuralNet4([46,30,26],[]);model.set_parameters(weights);model.eval()
    with torch.no_grad(): output=model(torch.zeros(46))
    results.append({'checkpoint':str(path.relative_to(args.root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'weight_shapes':[list(w.shape) for w in weights],'input_features':46,'output_actions':len(output),
                    'zero_input_output':output.tolist(),'weights_loaded_unchanged':True})
args.output.write_text(json.dumps({'status':'unsupported','reason':'Shipped weights have 46 inputs for bank, player 0, and four cards, plus 26 outputs. The upstream move selector uses four-card Splendor.py and player-0 input; no unchanged full 12-card multiplayer policy is supplied. Resizing, truncating or replacing it changes its policy.',
 'source_revision':'1a3713b95889e05f70c00e806698a6e8d59078f1','models':results,
 'method_discrepancy':'The pinned repository contains genetic/reinforcement training. No Double-DQN, prioritized replay or multi-step DQN implementation was found.'},indent=2)+'\n')
