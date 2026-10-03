"""Full capacity and semantic entity models. No simulator state is accepted."""
import math
import sys
from pathlib import Path

import torch
from torch import nn
import csv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/e95'))
from public_model import load as small_load


def normalized(x):
    y = x.clone()
    y[:, :392] *= .1
    y[:, 6] = x[:, 6] / 124
    return y


class ResidualBlock(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.norm = nn.LayerNorm(width)
        self.up = nn.Linear(width, width)
        self.down = nn.Linear(width, width)
        nn.init.zeros_(self.down.bias)

    def forward(self, h):
        return h + self.down(torch.nn.functional.gelu(self.up(self.norm(h)))) / math.sqrt(8)


class Capacity(nn.Module):
    def __init__(self, width=512, depth=8):
        super().__init__()
        self.stem = nn.Linear(525, width)
        self.blocks = nn.Sequential(*(ResidualBlock(width) for _ in range(depth)))
        self.norm = nn.LayerNorm(width)
        self.policy = nn.Linear(width, 81)
        self.value = nn.Linear(width, 2)

    def embedding(self, x, history=None):
        return self.norm(self.blocks(self.stem(normalized(x))))

    def forward(self, x, history=None):
        h = self.embedding(x, history)
        return self.policy(h), self.value(h).tanh()


def entities(x):
    """31 entities, 48 features. Cards combine their two old rows into one token."""
    y = normalized(x)
    r = y[:, :392].reshape(-1, 56, 7)
    tokens = x.new_zeros((len(x), 31, 48))
    tokens[:, 0, :7] = r[:, 0]  # bank and public turn
    tokens[:, 0, 7] = x[:, 519]  # public rules profile
    for p in range(2):
        tokens[:, 1+p, :7] = r[:, 34+p]
        tokens[:, 1+p, 7:14] = r[:, 42+p]
        tokens[:, 1+p, 14:35] = r[:, 36+3*p:39+3*p].flatten(1)
    for slot in range(12):
        tokens[:, 3+slot, :14] = r[:, 1+2*slot:3+2*slot].flatten(1)
        tokens[:, 3+slot, 14] = (slot//4+1)/3
    for slot in range(3):
        tokens[:, 15+slot, :7] = r[:, 31+slot]
    for p in range(2):
        for slot in range(3):
            i = 18+3*p+slot
            tokens[:, i, :14] = r[:, 44+6*p+2*slot:46+6*p+2*slot].flatten(1)
            tokens[:, i, 14] = p
            if p == 1:
                tokens[:, i, 15] = x[:, 512+slot]
                tokens[:, i, 16] = x[:, 515+slot]
    for tier in range(3):
        tokens[:, 24+tier, :7] = r[:, 25+2*tier]
        tokens[:, 24+tier, 7:47] = x[:, 392+40*tier:432+40*tier]
        tokens[:, 24+tier, 47] = (tier+1)/3
    # All reservation fields and otherwise unused row fields remain available.
    tokens[:, 27, :7] = x[:, 512:519]
    tokens[:, 28, :7] = r[:, 26]
    tokens[:, 29, :7] = r[:, 28]
    tokens[:, 30, :7] = r[:, 30]
    return tokens


_ENTITY_CACHE={}
def entities_fast(x):
    """Same semantic fields, one gather instead of many small device writes."""
    key=str(x.device)
    if key not in _ENTITY_CACHE:
        index=torch.zeros(31,48,dtype=torch.long)
        valid=torch.zeros(31,48,dtype=torch.bool)
        constant=torch.zeros(31,48)
        def fields(token,start,columns):
            columns=list(columns);index[token,start:start+len(columns)]=torch.tensor(columns)
            valid[token,start:start+len(columns)]=True
        fields(0,0,range(7));fields(0,7,[519])
        for p in range(2):
            fields(1+p,0,range((34+p)*7,(35+p)*7))
            fields(1+p,7,range((42+p)*7,(43+p)*7))
            fields(1+p,14,range((36+3*p)*7,(39+3*p)*7))
        for slot in range(12):
            fields(3+slot,0,range((1+2*slot)*7,(3+2*slot)*7))
            constant[3+slot,14]=(slot//4+1)/3
        for slot in range(3):fields(15+slot,0,range((31+slot)*7,(32+slot)*7))
        for p in range(2):
            for slot in range(3):
                i=18+3*p+slot
                fields(i,0,range((44+6*p+2*slot)*7,(46+6*p+2*slot)*7))
                constant[i,14]=p
                if p==1:fields(i,15,[512+slot,515+slot])
        for tier in range(3):
            fields(24+tier,0,range((25+2*tier)*7,(26+2*tier)*7))
            fields(24+tier,7,range(392+40*tier,432+40*tier))
            constant[24+tier,47]=(tier+1)/3
        fields(27,0,range(512,519))
        for i,row in enumerate((26,28,30)):fields(28+i,0,range(row*7,(row+1)*7))
        _ENTITY_CACHE[key]=(index.flatten().to(x.device),valid.to(x.device),constant.to(x.device))
    index,valid,constant=_ENTITY_CACHE[key]
    values=normalized(x).index_select(1,index).reshape(-1,31,48).masked_fill(~valid,0)
    return torch.where(constant!=0,constant,values)


class EntityTransformer(nn.Module):
    def __init__(self, width=256, depth=6, history=False):
        super().__init__()
        self.has_history = history
        self.fast_tokenization = False
        self.project = nn.Linear(48, width)
        self.identity = nn.Parameter(torch.randn(31, width)*.02)
        layer = nn.TransformerEncoderLayer(width, 8, 1024, dropout=0.,
                    activation='gelu', batch_first=True, norm_first=True)
        self.blocks = nn.TransformerEncoder(layer, depth, enable_nested_tensor=False)
        # PyTorch clones identical initial layers; use independent initialization.
        for block in self.blocks.layers:
            nn.init.xavier_uniform_(block.self_attn.in_proj_weight)
            nn.init.xavier_uniform_(block.linear1.weight)
            nn.init.xavier_uniform_(block.linear2.weight)
        self.norm = nn.LayerNorm(width)
        self.policy = nn.Linear(width, 81)
        self.value = nn.Linear(width, 2)
        if history:
            self.history_project = nn.Linear(32, width)
            self.history_position = nn.Parameter(torch.randn(16, width)*.02)
            self.opponent = nn.Linear(width, 81)
            self.belief = nn.Linear(width, 270)
            self.feedback = nn.Linear(351,width)
            nn.init.zeros_(self.feedback.weight)
            nn.init.zeros_(self.feedback.bias)
            with (ROOT/'data/cards.csv').open() as source:
                cards=list(csv.DictReader(source))
            self.register_buffer('tiers',torch.tensor([int(c['tier']) for c in cards]))

    def embedding(self, x, history=None):
        h = self.project(entities_fast(x) if self.fast_tokenization else entities(x)) + self.identity
        padding = None
        if self.has_history:
            if history is None:
                history = x.new_zeros((len(x), 16, 32))
            h = torch.cat((h, self.history_project(history)+self.history_position), dim=1)
            padding = torch.cat((torch.zeros((len(x),31),device=x.device,dtype=torch.bool),
                                 history[:, :, 0] == 0), dim=1)
        return self.norm(self.blocks(h, src_key_padding_mask=padding)[:, 0])

    def forward(self, x, history=None, pool=None):
        h = self.embedding(x, history)
        if self.has_history:
            opponent=self.opponent(h)
            beliefs=self.belief(h).reshape(-1,3,90)
            if pool is None:
                pool=x.new_ones((len(x),90))
            tier=torch.round(x[:,515:518]*3).long()
            allowed=(pool[:,None,:]>0)&(tier[:,:,None]==self.tiers[None,None,:])
            active=x[:,512:515]>0
            allowed=torch.where(active[:,:,None],allowed,torch.ones_like(allowed))
            beliefs=beliefs.masked_fill(~allowed,-1e9)
            h=h+self.feedback(torch.cat((opponent.softmax(-1),beliefs.softmax(-1).flatten(1)),dim=-1))
            return self.policy(h),self.value(h).tanh(),opponent,beliefs
        return self.policy(h), self.value(h).tanh()


def create(kind):
    if kind in ('small','small-cold'):
        model=small_load(ROOT/'research/e81/model/model.pt')
        if kind=='small-cold':
            for module in model.modules():
                if hasattr(module,'reset_parameters'):
                    module.reset_parameters()
        return model
    if kind == 'capacity':
        return Capacity()
    if kind in ('entity', 'history'):
        return EntityTransformer(history=kind == 'history')
    raise ValueError(kind)


def forward(model, kind, x, history=None, pool=None):
    if kind in ('small','small-cold'):
        from flywheel_model import raw
        return raw(model, x)
    if kind=='history':return model(x,history,pool)
    return model(x, history)


def load(path, device='cpu'):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    model = create(payload['kind'])
    model.load_state_dict(payload['state_dict'], strict=True)
    if hasattr(model,'fast_tokenization'):model.fast_tokenization=payload.get('fast_entities',False)
    return model.to(device).eval(), payload
