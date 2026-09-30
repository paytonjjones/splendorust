"""Independent policy features and an exact frozen bootstrap critic."""
import copy
import struct
import tempfile
from pathlib import Path
import torch
from flywheel_model import bootstrap,export,expand_trunk

class SplitBootstrap(torch.nn.Module):
    def __init__(self,warmstart=None):
        super().__init__()
        payload=torch.load(warmstart,map_location='cpu',weights_only=True) if warmstart else None
        split=payload is not None and payload.get('architecture')=='split-bootstrap'
        self.policy=bootstrap(None if split else warmstart)
        self.critic=copy.deepcopy(self.policy)
        if split:
            expand_trunk(self.policy,payload['policy_trunk_blocks'])
            expand_trunk(self.critic,payload['critic_trunk_blocks'])
            self.load_state_dict(payload['state_dict'],strict=True)
        for p in self.critic.parameters():p.requires_grad_(False)
        for p in self.policy.output_layers_V.parameters():p.requires_grad_(False)
        self.train(False)

    def train(self,mode=True):
        super().train(mode)
        self.critic.eval()
        self.policy.output_layers_V.eval()
        return self

    def forward(self,x):
        h=self.policy.trunk(self.policy.first_layer(x.reshape(-1,56,7)))
        policy=self.policy.output_layers_PI(h)
        with torch.no_grad():
            h=self.critic.trunk(self.critic.first_layer(x.reshape(-1,56,7)))
            value=self.critic.output_layers_V(h).tanh()
        return policy,value

def export_split(model,path):
    with tempfile.TemporaryDirectory() as directory:
        directory=Path(directory)
        export(model.policy,directory/'policy.bin')
        export(model.critic,directory/'critic.bin')
        policy=(directory/'policy.bin').read_bytes();critic=(directory/'critic.bin').read_bytes()
    Path(path).write_bytes(b'SPDUAL01'+struct.pack('<II',len(policy),len(critic))+policy+critic)
