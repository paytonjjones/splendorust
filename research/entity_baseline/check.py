"""Check the exact parent, token gather, and public-position policy/value output."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research/architecture_pivots'))
from models import load, entities, entities_fast
sys.path.insert(0, str(ROOT / 'research/e95'))
from public_model import inputs

torch.set_num_threads(1)
assert hashlib.sha256((HERE / 'model.pt').read_bytes()).hexdigest() == 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'
model, payload = load(HERE / 'model.pt')
assert payload['kind'] == 'entity' and payload['epoch'] == 12
assert sum(p.numel() for p in model.parameters()) == 4780883
assert len(model.blocks.layers) == 6 and model.project.out_features == 256
assert all(layer.self_attn.num_heads == 8 for layer in model.blocks.layers)
assert not model.has_history
reference = json.loads((HERE / 'parity.json').read_text())
x = torch.from_numpy(inputs(np.array(reference['x'], dtype=np.float32),
                           np.array(reference['context'], dtype=np.float32), True))
assert torch.equal(entities(x), entities_fast(x))
with torch.inference_mode():
    logits, values = model(x)
assert torch.isfinite(logits).all() and torch.isfinite(values).all()
assert torch.allclose(logits, torch.tensor(reference['logits']), atol=1e-6, rtol=1e-6)
assert torch.allclose(values, torch.tensor(reference['values']), atol=1e-6, rtol=1e-6)
print(json.dumps(dict(kind=payload['kind'], selected_epoch=payload['epoch'], parameters=4780883,
                      public_fixtures=len(x), policy_shape=list(logits.shape), value_shape=list(values.shape),
                      checkpoint_sha256=hashlib.sha256((HERE / 'model.pt').read_bytes()).hexdigest())))
