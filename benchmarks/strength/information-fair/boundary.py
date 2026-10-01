"""Information interventions only. Never modify the native referee or AlphaZero."""
import hashlib
import json
import sys
from pathlib import Path
NATIVE = Path(__file__).resolve().parents[1] / "native"
sys.path.insert(1, str(NATIVE))
from upstream import ROOT, Upstream, Tracker, sha, stream
from validate import RPC

ARMS = ("control", "blind-alpha", "privileged-sr")

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def privileged_input(tracker, state, seat):
    # Sorted card lists represent sets, never a future draw sequence.
    return tracker.fixture(state, seat)

def blind_input(rpc, observation, seed, np):
    # The public worker rejects hidden identities and unknown fields. Its sampler
    # jointly assigns unknown reservations and decks without replacement.
    sample = rpc.call(op="sample", observation=observation, seed=seed)
    assert sample["observation"] == observation
    board = np.asarray(sample["features"], dtype=np.int8).reshape(56, 7)
    return board
