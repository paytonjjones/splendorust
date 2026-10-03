"""History and auxiliary extension for the residual winner, if selected."""
import csv
import torch
from torch import nn
from models import Capacity, ROOT
from models import create as base_create, forward as base_forward, load as base_load


class CapacityHistory(Capacity):
    def __init__(self):
        super().__init__()
        width = 256
        self.history_state = nn.Linear(512, width)
        self.history_project = nn.Linear(32, width)
        self.history_position = nn.Parameter(torch.randn(16, width) * .02)
        layer = nn.TransformerEncoderLayer(width, 8, 1024, dropout=0.,
            activation='gelu', batch_first=True, norm_first=True)
        self.history_blocks = nn.TransformerEncoder(layer, 4, enable_nested_tensor=False)
        for block in self.history_blocks.layers:
            nn.init.xavier_uniform_(block.self_attn.in_proj_weight)
            nn.init.xavier_uniform_(block.linear1.weight)
            nn.init.xavier_uniform_(block.linear2.weight)
        self.history_norm = nn.LayerNorm(width)
        self.history_feedback = nn.Linear(width, 512)
        self.opponent = nn.Linear(512, 81)
        self.belief = nn.Linear(512, 270)
        self.feedback = nn.Linear(351, 512)
        for module in (self.history_feedback, self.feedback):
            nn.init.zeros_(module.weight)
            nn.init.zeros_(module.bias)
        with (ROOT / 'data/cards.csv').open() as source:
            cards = list(csv.DictReader(source))
        self.register_buffer('tiers', torch.tensor([int(c['tier']) for c in cards]))

    def embedding(self, x, history=None):
        state = super().embedding(x)
        if history is None:
            history = x.new_zeros((len(x), 16, 32))
        tokens = torch.cat((self.history_state(state)[:, None],
            self.history_project(history) + self.history_position), dim=1)
        padding = torch.cat((torch.zeros((len(x), 1), device=x.device, dtype=torch.bool),
            history[:, :, 0] == 0), dim=1)
        context = self.history_norm(self.history_blocks(tokens, src_key_padding_mask=padding)[:, 0])
        return state + self.history_feedback(context)

    def forward(self, x, history=None, pool=None):
        h = self.embedding(x, history)
        opponent = self.opponent(h)
        beliefs = self.belief(h).reshape(-1, 3, 90)
        if pool is None:
            pool = x.new_ones((len(x), 90))
        tier = torch.round(x[:, 515:518] * 3).long()
        allowed = (pool[:, None, :] > 0) & (tier[:, :, None] == self.tiers[None, None, :])
        active = x[:, 512:515] > 0
        allowed = torch.where(active[:, :, None], allowed, torch.ones_like(allowed))
        beliefs = beliefs.masked_fill(~allowed, -1e9)
        h = h + self.feedback(torch.cat((opponent.softmax(-1), beliefs.softmax(-1).flatten(1)), dim=-1))
        return self.policy(h), self.value(h).tanh(), opponent, beliefs


def create(kind):
    return CapacityHistory() if kind == 'history' else base_create(kind)


def forward(model, kind, x, history=None, pool=None):
    return base_forward(model, kind, x, history, pool)


def load(path, device='cpu'):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    if payload.get('backbone') != 'capacity' or payload['kind'] != 'history':
        return base_load(path, device)
    model = CapacityHistory()
    model.load_state_dict(payload['state_dict'], strict=True)
    return model.to(device).eval(), payload
