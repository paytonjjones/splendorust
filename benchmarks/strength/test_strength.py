import importlib.util,json,tempfile,unittest
from pathlib import Path
from summarize import summarize
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runner',ROOT/'benchmarks/strength/run.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class SummaryTest(unittest.TestCase):
 def write(self,rows):
  p=Path(self.tmp.name)/'run.jsonl';p.write_text('\n'.join(map(json.dumps,[{'games':len(rows),'players':2,'candidate':'search'}]+rows)));return p
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.rows=[{'rotation':i,'setup_seed':42,'seats':['search','random'] if i==0 else ['random','search'],
              'status':'complete','rewards':[1,0] if i==0 else [0,1]} for i in range(2)]
 def test_pair_not_two_independent_games(self):
  s=summarize(self.write(self.rows));self.assertEqual(s['setup_blocks'],1);self.assertEqual(s['paired_bootstrap95_missing_envelope'],[1,1])
 def test_missing_is_not_a_win(self):
  self.rows[1].update(status='unsupported',rewards=None)
  s=summarize(self.write(self.rows));self.assertEqual(s['all_requested_credit_bounds'],[.5,1]);self.assertEqual(s['candidate_credit_total'],1)
 def test_native_no_winner(self):
  self.rows[1]['rewards']=[0,0];s=summarize(self.write(self.rows));self.assertEqual(s['statuses']['native_no_winner'],1)
 def test_bad_rotation_rejected(self):
  self.rows[1]['seats']=['search','random']
  with self.assertRaises(ValueError):summarize(self.write(self.rows))
class NativePairTest(unittest.TestCase):
 def make(self,fixtures):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  path=Path(self.tmp.name)/'native.jsonl'
  rows=[{'rotation':i,'setup_seed':42,'seats':['seal256_mcts','random'] if i==0 else ['random','seal256_mcts'],
         'status':'complete','rewards':[1,0] if i==0 else [0,1],'initial_state':fixture} for i,fixture in enumerate(fixtures)]
  path.write_text('\n'.join(map(json.dumps,[{'games':2,'engine':'seal256_native','paired_initial_states':True}]+rows)))
  return path
 def test_native_fixture_pair(self):
  s=summarize(self.make([{'cards':[1,2]},{'cards':[1,2]}]));self.assertTrue(s['pairing_verified'])
 def test_native_different_setups_rejected(self):
  with self.assertRaises(ValueError):summarize(self.make([{'cards':[1,2]},{'cards':[2,1]}]))
class WorkerTest(unittest.TestCase):
 def test_repeated_observation_and_sampling(self):
  with tempfile.TemporaryDirectory() as d:
   rpc=runner.RPC([ROOT/'target/release/examples/strength_worker'],Path(d)/'core.log')
   try:
    rpc.call('reset',players=2,seed=1,sampling_seed=123,agent_seed=12,agent_seeds=[12,13],iterations=128,seats=['search','random'])
    before=rpc.call('observe');sample=rpc.call('sample');after=rpc.call('observe')
    self.assertEqual(before,after);self.assertNotIn('seed',sample);self.assertNotIn('decks',sample)
    self.assertTrue(sample['sampled_hidden_world'])
    for _ in range(12):
     state=rpc.call('observe');chosen=rpc.call('select')['action'];self.assertIn(chosen,state['legal']);rpc.call('apply',action=chosen)
    before=rpc.call('observe')
    # Check the public observation remains unchanged after another hidden sample.
    rpc.call('sample');self.assertEqual(before,rpc.call('observe'))
   finally:rpc.close()
if __name__=='__main__':unittest.main()
