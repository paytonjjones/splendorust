#!/usr/bin/env python3
"""Export the exact upstream version-80 network for native Rust inference.
Architecture copyright (c) 2018 Surag Nair, MIT; see e30/UPSTREAM-LICENSE.
"""
import hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
root=Path('local/strength/external/alphazero').resolve()
sys.path.insert(0,str(root))
checkpoint=root/'splendor/pretrained_2players.pt'
p=torch.load(checkpoint,map_location='cpu',weights_only=False)
assert p['nn_version']==80
model=p['full_model'].cpu().eval()
model.load_state_dict(p['state_dict'],strict=True)
assert all(torch.equal(v,p['state_dict'][k]) for k,v in model.state_dict().items())
output=Path('research/e30'); output.mkdir(exist_ok=True)
values=[]; layers=[]
def put(a):
    a=np.asarray(a,dtype='<f4');values.append(a.reshape(-1));return a.size

def linear(layer):
    assert layer.bias is not None
    layers.append(dict(kind='linear',shape=list(layer.weight.shape)))
    put(layer.weight.detach().numpy());put(layer.bias.detach().numpy())

def norm(layer):
    layers.append(dict(kind='norm',shape=list(layer.linear.weight.shape),depthwise=layer.depthwise,channels=layer.norm.num_features))
    put(layer.linear.weight.detach().numpy())
    n=layer.norm
    scale=n.weight.detach()/torch.sqrt(n.running_var+n.eps)
    bias=n.bias.detach()-n.running_mean*scale
    put(scale.numpy());put(bias.numpy())

def block(layer):
    norm(layer.expand);norm(layer.depthwise)
    linear(layer.se.fc1);linear(layer.se.fc2)
    norm(layer.project)

norm(model.first_layer);block(model.trunk[0])
for head in (model.output_layers_PI,model.output_layers_V):
    block(head[0]);linear(head[2]);linear(head[4])
np.concatenate(values).astype('<f4').tofile(output/'model.bin')
from splendor import SplendorGame as gm
gm.NUMBER_PLAYERS=2
game=gm.SplendorGame()
np.random.seed(616000007);torch.manual_seed(614000007)
boards=[game.getInitBoard().astype(np.float32) for _ in range(8)]
boards += [np.random.randint(-128,20,(56,7)).astype(np.float32) for _ in range(8)]
x=torch.tensor(np.stack(boards))
with torch.no_grad():
    h=model.trunk(model.first_layer(x))
    logits=model.output_layers_PI(h);v=model.output_layers_V(h).tanh()
(output/'parity.json').write_text(json.dumps(dict(x=x.reshape(-1,392).tolist(),logits=logits.tolist(),values=v.tolist())))
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
(output/'manifest.json').write_text(json.dumps(dict(upstream_revision='32a27ac1f85d5de2766cc5f60c2bf04e557f7836',checkpoint_sha256=sha(checkpoint),model_sha256=sha(output/'model.bin'),script_sha256=sha(__file__),architecture=80,torch=torch.__version__,parameters=sum(v.numel() for v in model.parameters()),layers=layers,fixture_seed=616000007,scope='Inference parity only; not training or a playing-strength result'),indent=2)+'\n')
