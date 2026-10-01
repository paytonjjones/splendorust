"""Information boundary, fixed-policy parity, and exact-partition tests."""
import copy
import tempfile
import unittest
from pathlib import Path
from boundary import ROOT, Upstream, Tracker, RPC, blind_input, privileged_input, stream

MODEL = ROOT / 'research/e81/model/model.bin'

class InformationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u = Upstream(network=True)

    def setUp(self):
        self.public = RPC([ROOT/'target/release/examples/native_policy_worker', MODEL])
        self.privileged = RPC([ROOT/'target/release/examples/privileged_native_worker', MODEL])
        self.addCleanup(self.public.close)
        self.addCleanup(self.privileged.close)

    def worlds(self):
        u = self.u
        initial = u.setup(4890000001)
        result = []
        for seed in range(100, 110):
            state, seat = u.apply(initial, 0, 24, seed, deterministic=True)
            tracker = Tracker(u, initial)
            tracker.update(initial, state, 0, 24)
            result.append((state, seat, tracker))
        return result

    def test_blind_inputs_and_full800_choices_are_hidden_world_invariant(self):
        u = self.u
        worlds = self.worlds()
        observations = [t.snapshot(s, seat) for s, seat, t in worlds]
        self.assertTrue(all(o == observations[0] for o in observations))
        self.assertTrue(any(not u.np.array_equal(worlds[0][0], s) for s, _, _ in worlds))
        boards = [blind_input(self.public, o, 78910, u.np) for o in observations]
        self.assertTrue(all(u.np.array_equal(b, boards[0]) for b in boards))
        choices = []
        for board in boards[:2]:
            u.reset_policy(989898)
            choices.append(u.choose(board, 0))
            self.assertEqual(u.tree.step, 799)
        self.assertEqual(choices[0], choices[1])
        # No actual world is passed to either the sampler or upstream choose.
        self.assertEqual(u.config.numMCTSSims, 800)
        self.assertEqual(u.config.universes, 3)

    def test_blind_sampler_has_full_support_and_rejects_hidden_fields(self):
        u = self.u
        state, seat, t = self.worlds()[0]
        o = t.snapshot(state, seat)
        cards = set()
        for seed in range(512):
            b = blind_input(self.public, o, seed, u.np)
            # Input features are canonical: opponent is relative seat 1.
            cards.add(u.cid(b[50:52]))
            self.assertEqual(u.legal(b, 0), u.legal(state, seat))
            u.game.board.copy_state(b, False)
            self.assertEqual([int(u.game.board.nb_deck_tiers[2*i,:5].sum()) for i in range(3)], o['remaining'])
        known = set(o['market']) | set(o['players'][seat]['owned'])
        expected = {i for i, c in enumerate(u.data['cards']) if c['tier'] == 0 and i not in known}
        self.assertEqual(cards, expected)
        for key in ['decks', 'setup_seed', 'rng', 'deck_order']:
            bad = copy.deepcopy(o); bad[key] = 1
            with self.assertRaises(RuntimeError):
                blind_input(self.public, bad, 1, u.np)
        bad = t.snapshot(state, seat, full=True)
        with self.assertRaises(RuntimeError):
            blind_input(self.public, bad, 1, u.np)

    def test_no_unknown_cards_reproduces_unchanged_native_board_and_preserves_public_memory(self):
        u = self.u
        state = u.setup(4890000002); t = Tracker(u, state); seat = 0
        for turn, action in enumerate([12, 13, 30, 31]):
            # Public reservations remain known to the other player.
            o = t.snapshot(state, seat)
            board = blind_input(self.public, o, turn, u.np)
            self.assertTrue(u.np.array_equal(board, u.game.getCanonicalForm(state, seat)))
            child, nxt = u.apply(state, seat, action, 111+turn)
            t.update(state, child, seat, action); state, seat = child, nxt
        self.assertTrue(t.snapshot(state, seat)['players'][1-seat]['reserved'][0]['public'])

    def test_privileged_exact_features_and_set_order_independence(self):
        u = self.u
        outputs = []
        for state, seat, t in self.worlds()[:3]:
            payload = privileged_input(t, state, seat)
            result = self.privileged.call(op='sample', **payload)
            self.assertEqual(result['features'], u.game.getCanonicalForm(state, seat).astype(float).flatten().tolist())
            self.assertEqual(result['public_observation'], t.snapshot(state, seat))
            shuffled = copy.deepcopy(payload)
            for deck in shuffled['decks']: deck.reverse()
            self.assertEqual(result, self.privileged.call(op='sample', **shuffled))
            legal = u.legal(state, seat)
            choices = []
            for p in [payload, shuffled]:
                self.privileged.call(op='reset', seed=987654, iterations=128, depth=16, search='gumbel')
                choices.append(self.privileged.call(op='choose', **p, legal=legal))
            self.assertEqual(choices[0], choices[1])
            self.assertEqual(choices[0]['simulations'], 128)
            outputs.append(result['features'])
        self.assertTrue(any(x != outputs[0] for x in outputs[1:]))
        state, seat, t = self.worlds()[0]
        payload = privileged_input(t, state, seat)
        for change in ['duplicate', 'wrong-tier', 'missing', 'order', 'seed']:
            bad = copy.deepcopy(payload)
            if change == 'duplicate': bad['decks'][0].append(bad['decks'][0][0])
            elif change == 'wrong-tier': bad['decks'][1].append(bad['decks'][0].pop())
            elif change == 'missing': bad['decks'][0].pop()
            elif change == 'order': bad['deck_order'] = bad['decks']
            else: bad['setup_seed'] = 123
            with self.assertRaises(RuntimeError): self.privileged.call(op='sample', **bad)

    def test_public_worker_matches_immutable_main_worker(self):
        baseline = RPC([ROOT/'local/strength/control-source/target/release/examples/native_policy_worker', MODEL])
        self.addCleanup(baseline.close)
        u = self.u
        for search in ['puct', 'gumbel']:
            state = u.setup(4890000003); t = Tracker(u, state); seat = 0
            for turn in range(12):
                o = t.snapshot(state, seat); legal = u.legal(state, seat)
                results = []
                for rpc in [self.public, baseline]:
                    rpc.call(op='reset', seed=87654+turn, iterations=128, depth=16, search=search)
                    results.append(rpc.call(op='choose', observation=o, legal=legal))
                self.assertEqual(results[0], results[1])
                action = 24 if turn < 2 else results[0]['action']
                child, nxt = u.apply(state, seat, action, 222+turn)
                t.update(state, child, seat, action); state, seat = child, nxt

    def test_unchanged_alpha_call_is_exact(self):
        u = self.u
        for state, seat, t in self.worlds()[:2]:
            u.reset_policy(654321); old = u.choose(state, seat)
            u.reset_policy(654321); board = u.game.getCanonicalForm(state, seat).copy()
            new = u.choose(board, 0)
            self.assertEqual(old, new)

if __name__ == '__main__':
    # Keep upstream temporary ONNX exports isolated.
    import os
    with tempfile.TemporaryDirectory(prefix='information-tests-') as tmp:
        os.chdir(tmp)
        unittest.main()
