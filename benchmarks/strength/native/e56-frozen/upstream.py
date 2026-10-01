"""Load the pinned, unmodified native engine and pit.py player settings."""
import contextlib
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'local/strength/external/alphazero'
PIN = '32a27ac1f85d5de2766cc5f60c2bf04e557f7836'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def stream(master, label, block, identity=0):
    # No reversible relationship between public policy RNG and setup stream.
    return int.from_bytes(hashlib.sha256(f'native-v1:{master}:{label}:{block}:{identity}'.encode()).digest()[:8], 'little')

class Upstream:
    def __init__(self, network=False):
        actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
        if actual != PIN or dirty:
            raise RuntimeError('require pinned clean AlphaZero source')
        sys.path.insert(0, str(SOURCE))
        import numpy as np
        from numba import njit
        from splendor import SplendorGame as game_module
        game_module.NUMBER_PLAYERS = 2
        from splendor.SplendorLogic import np_all_cards_1, np_all_cards_2, np_all_cards_3
        self.np, self.game = np, game_module.SplendorGame()
        @njit
        def seed_numba(seed):
            np.random.seed(seed)
        self.seed_numba = seed_numba
        # Use canonical metadata supplied by the existing benchmark worker.
        process = subprocess.run([ROOT/'target/release/examples/strength_worker'], input='{"op":"data"}\n', capture_output=True, text=True, check=True)
        self.data = json.loads(process.stdout)
        self.card_lookup = {}
        self.card_native = {}
        for cid, c in enumerate(self.data['cards']):
            for group, row in enumerate((np_all_cards_1, np_all_cards_2, np_all_cards_3)[c['tier']]):
                for slot, native in enumerate(row):
                    if list(native[0, :5]) == c['cost'] and native[1, c['bonus']] == 1 and native[1, 6] == c['points']:
                        self.card_lookup[native.tobytes()] = cid
                        self.card_native[cid] = (c['tier'], group, slot)
        assert len(self.card_lookup) == len(self.card_native) == 90
        self.noble_lookup = {tuple(n['cost']): i for i, n in enumerate(self.data['nobles'])}
        if network:
            import torch
            from splendor.NNet import NNetWrapper
            from MCTS import MCTS
            from utils import dotdict
            self.torch, self.MCTS = torch, MCTS
            with contextlib.redirect_stdout(sys.stderr):
                self.net = NNetWrapper(self.game, dict(lr=None, dropout=0., epochs=None, batch_size=None, nn_version=-1))
                checkpoint = self.net.load_checkpoint(str(SOURCE/'splendor'), 'pretrained_2players.pt')
            assert self.net.nnet.state_dict().keys() == checkpoint['state_dict'].keys()
            for name, value in checkpoint['state_dict'].items():
                assert torch.equal(self.net.nnet.state_dict()[name], value), name
            cpuct = checkpoint['cpuct']
            self.config = dotdict(dict(numMCTSSims=checkpoint['numMCTSSims'], fpu=checkpoint['fpu'],
                universes=checkpoint['universes'], cpuct=float(cpuct[0]) if isinstance(cpuct, list) else cpuct,
                prob_fullMCTS=1., forced_playouts=False, no_mem_optim=False))

    def setup(self, seed):
        self.seed_numba(seed % 2**32)
        return self.game.getInitBoard().copy()

    def reset_policy(self, seed):
        self.np.random.seed(seed % 2**32)
        random.seed(seed)
        self.torch.manual_seed(seed)
        self.tree = self.MCTS(self.game, self.net, self.config)
        self.tree.rng = self.np.random.default_rng(seed)

    def choose(self, state, current):
        canonical = self.game.getCanonicalForm(state, current).copy()
        turns = int(state[0, 6].astype(self.np.uint8))
        # Exact pinned pit.py player call, total-turn temperature schedule.
        with contextlib.redirect_stdout(sys.stderr):
            probs = self.tree.getActionProb(canonical, temp=.5 if turns+1 <= 6 else 0., force_full_search=True)[0]
        return int(self.np.argmax(probs))

    def legal(self, state, current):
        return list(map(int, self.np.flatnonzero(self.game.getValidMoves(state, current))))

    def rewards(self, state, current):
        rewards = self.game.getGameEnded(state, current)
        return list(map(float, rewards)) if rewards.any() else None

    def apply(self, state, current, action, chance_seed, deterministic=False):
        if not deterministic:
            self.seed_numba(chance_seed % 2**32)
        nxt, seat = self.game.getNextState(state, current, action, random_seed=chance_seed if deterministic else 0)
        return nxt.copy(), int(seat)

    def cid(self, rows):
        return 255 if not rows.any() else self.card_lookup[rows.tobytes()]

class Tracker:
    """Public memory of revealed purchases, reservation tiers and visibility."""
    def __init__(self, upstream, state):
        self.u = upstream
        self.owned = [[], []]
        self.reservations = [[], []]
        upstream.game.board.copy_state(state, False)
        self.noble_ids = [upstream.noble_lookup[tuple(row[:5])] for row in upstream.game.board.nobles]

    def update(self, before, after, seat, action):
        self.u.game.board.copy_state(before, False)
        board = self.u.game.board
        if action < 12:
            self.owned[seat].append(self.u.cid(board.cards_tiers[2*action:2*action+2]))
        elif 12 <= action < 24:
            self.reservations[seat].append(dict(tier=(action-12)//4, public=True))
        elif 24 <= action < 27:
            self.reservations[seat].append(dict(tier=action-24, public=False))
        elif 27 <= action < 30:
            slot = action-27
            self.owned[seat].append(self.u.cid(board.players_reserved[6*seat+2*slot:6*seat+2*slot+2]))
            del self.reservations[seat][slot]

    def snapshot(self, state, current, viewer=None, full=False):
        viewer = current if viewer is None else viewer
        self.u.game.board.copy_state(state, False)
        b = self.u.game.board
        mask = lambda rows: sum(1 << i for i, row in enumerate(rows) if row.any())
        players = []
        for seat in range(2):
            reserved = []
            for slot in range(3):
                if slot < len(self.reservations[seat]):
                    meta = self.reservations[seat][slot]
                    cid = self.u.cid(b.players_reserved[6*seat+2*slot:6*seat+2*slot+2])
                    reserved.append(dict(card=cid if full or seat == viewer or meta['public'] else 255, **meta))
                else:
                    reserved.append(dict(card=255, tier=0, public=False))
            players.append(dict(tokens=list(map(int, b.players_gems[seat, :6])),
                bonuses=list(map(int, b.players_cards[seat, :5])), card_points=int(b.players_cards[seat, 6]),
                owned=sorted(self.owned[seat]), nobles=mask(b.players_nobles[3*seat:3*seat+3]),
                reserved=reserved, reserved_count=len(self.reservations[seat])))
        return dict(viewer=viewer, current=current, turns=int(b.bank[0, 6].astype(self.u.np.uint8)),
            bank=list(map(int, b.bank[0, :6])), market=[self.u.cid(b.cards_tiers[2*i:2*i+2]) for i in range(12)],
            remaining=[int(b.nb_deck_tiers[2*tier, :5].sum()) for tier in range(3)],
            noble_ids=self.noble_ids, nobles=mask(b.nobles), players=players)

    def fixture(self, state, current):
        observation = self.snapshot(state, current, full=True)
        self.u.game.board.copy_state(state, False)
        decks = [[], [], []]
        for cid, (tier, group, slot) in self.u.card_native.items():
            bits = int(self.u.game.board.nb_deck_tiers[2*tier+1, group].astype(self.u.np.uint8))
            if bits & (128 >> slot):
                decks[tier].append(cid)
        return dict(observation=observation, decks=decks)
