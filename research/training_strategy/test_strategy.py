import sys
import unittest
from pathlib import Path
import numpy as np
import torch
from data import DTYPE, ROOT, validate
from strategy_train import policy_loss, q_loss, value_target
sys.path.insert(0, str(ROOT / 'research/architecture_pivots'))
from models import create, load


class Labels(unittest.TestCase):
    def row(self):
        r = np.zeros(1, dtype=DTYPE)
        r['mask'][0, :3] = 1
        r['visits'][0, :2] = [3, 1]
        r['q'].fill(np.nan)
        r['q'][0, :2] = [.75, .25]
        r['root'] = .625
        r['network'] = .5
        r['action'] = 0
        r['outcome'] = 1
        r['full'] = 1
        return r

    def test_visit_and_q_contract(self):
        r = self.row()
        self.assertTrue(validate(r)[0])
        r['q'][0, 2] = 0
        with self.assertRaises(AssertionError): validate(r)
        r = self.row()
        r['mask'][0, 1] = 0
        with self.assertRaises(AssertionError): validate(r)
        r = self.row()
        r['root'] = .75
        with self.assertRaises(AssertionError): validate(r)

    def test_incomplete_and_cheap_rows_have_no_training_outcome(self):
        r = self.row()
        r['outcome'] = np.nan
        self.assertFalse(validate(r)[0])
        r = self.row()
        r['full'] = 0
        self.assertFalse(validate(r)[0])

    def test_q_loss_has_no_unknown_edge_gradient(self):
        p = torch.zeros(1, 3, requires_grad=True)
        q = torch.tensor([[.75, .25, float('nan')]])
        mask = torch.tensor([[True, True, False]])
        loss = q_loss(p, q, mask).mean()
        self.assertAlmostEqual(loss.item(), .25)
        loss.backward()
        self.assertTrue(torch.equal(p.grad, torch.tensor([[-.5, .5, 0.]])))
        p2 = torch.tensor([[0., 0., 100.]])
        self.assertEqual(q_loss(p2, q, mask).item(), loss.item())

    def test_value_sign_and_mix(self):
        self.assertAlmostEqual(value_target(torch.tensor(1.), torch.tensor(1.)).item(), 1.)
        self.assertAlmostEqual(value_target(torch.tensor(0.), torch.tensor(0.)).item(), -1.)
        self.assertAlmostEqual(value_target(torch.tensor(.5), torch.tensor(1.)).item(), 1/1.837, places=6)

    def test_masked_policy_gradient_and_soft_targets(self):
        logits = torch.zeros(1, 3, requires_grad=True)
        loss, _ = policy_loss(logits, torch.tensor([[1., 1., 0.]]), torch.tensor([[.75, .25, 0.]]))
        loss.mean().backward()
        self.assertTrue(torch.equal(logits.grad, torch.tensor([[-.25, .25, 0.]])))


class EntityOutput(unittest.TestCase):
    def test_parent_identity_q_gradients_and_runtime_stripping(self):
        torch.set_num_threads(1)
        torch.manual_seed(800000041)
        parent, _ = load(ROOT / 'research/entity_baseline/model.pt')
        model = create('entity-q')
        missing, extra = model.load_state_dict(parent.state_dict(), strict=False)
        self.assertEqual(set(missing), {'action_q.weight', 'action_q.bias'})
        self.assertFalse(extra)
        x = torch.randn(2, 525)
        x[:, 519] = 0
        parent.eval(); model.eval()
        with torch.no_grad():
            p, v = parent(x)
            pp, vv, q = model(x)
        self.assertTrue(torch.equal(p, pp) and torch.equal(v, vv))
        self.assertTrue(torch.equal(q, torch.zeros_like(q)))
        (_, _, q) = model(x)
        q.square().sum().backward()
        model.zero_grad(set_to_none=True)
        (_, _, q) = model(x)
        (q - .5).square().mean().backward()
        self.assertGreater(model.action_q.weight.grad.abs().sum().item(), 0)
        # Zero Q head has zero trunk gradient at initialization; after one head
        # update Q supervision must reach the shared trunk.
        with torch.no_grad(): model.action_q.weight.add_(-.01 * model.action_q.weight.grad)
        model.zero_grad(set_to_none=True)
        model(x)[2].square().mean().backward()
        self.assertGreater(model.project.weight.grad.abs().sum().item(), 0)
        runtime = create('entity')
        runtime.load_state_dict({k:v for k,v in model.state_dict().items() if not k.startswith('action_q.')})
        runtime.eval()
        with torch.no_grad():
            a, b, _ = model(x)
            aa, bb = runtime(x)
        self.assertTrue(torch.equal(a, aa) and torch.equal(b, bb))


if __name__ == '__main__':
    unittest.main()
