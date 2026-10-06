"""FP32 token-to-output measurements of the frozen Entity model, with CPU readback."""
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'research/architecture_pivots'), str(ROOT / 'research/e95')]
from models import load
pointer = json.loads((ROOT / 'research/STRENGTH_CHAMPION.json').read_text())
checkpoint = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / pointer['checkpoint']
assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == pointer['checkpoint_sha256']
model, _ = load(checkpoint, 'mps')
fixtures = json.loads((ROOT / 'research/webgpu-20261006/fixtures.json').read_text())
def run(tokens):
    h = model.project(torch.from_numpy(tokens).to('mps')) + model.identity
    h = model.norm(model.blocks(h)[:, 0])
    return torch.cat((model.policy(h), model.value(h).tanh()), dim=-1).cpu().numpy()
results = []
with torch.inference_mode():
    errors = []
    for f in fixtures:
        out = run(np.array(f['tokens'], dtype=np.float32).reshape(1,31,48))[0]
        assert np.isfinite(out).all()
        errors.append([float(np.max(np.abs(out[:81] - f['logits']))), float(np.max(np.abs(out[81:] - f['values'])))])
    assert max(e[0] for e in errors) < .001 and max(e[1] for e in errors) < .0001
    for batch in [1,32]:
        batches = [np.array([fixtures[(start + i) % len(fixtures)]['tokens'] for i in range(batch)], dtype=np.float32).reshape(batch,31,48) for start in range(len(fixtures))]
        for i in range(10): run(batches[i % len(batches)])
        times = []
        for i in range(500):
            torch.mps.synchronize()
            start = time.perf_counter()
            run(batches[i % len(batches)])
            torch.mps.synchronize()
            times.append((time.perf_counter()-start)*1000)
        results.append(dict(batch=batch, measuredCalls=len(times), medianMs=statistics.median(times), p95Ms=sorted(times)[475], meanMs=statistics.mean(times), rowsPerSecond=batch*1000/statistics.median(times)))
receipt = dict(checkpointSha256=pointer['checkpoint_sha256'], precision='float32', torch=torch.__version__, includes='CPU tokens to MPS, forward, CPU output readback; excludes public tokenization and service queue', maxLogitError=max(e[0] for e in errors), maxValueError=max(e[1] for e in errors), measurements=results)
(ROOT / 'research/webgpu-20261006/native-profile.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt))
