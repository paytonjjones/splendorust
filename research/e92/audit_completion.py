"""Audit the actual post-test build captured by every arena shard."""
import json,hashlib,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent;plan=json.loads((out/'plan.json').read_text());summary=json.loads((out/'summary.json').read_text());meta=summary['metadata'];sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
changed=[]
for p,h in plan['files'].items():
 if sha(p)!=h:changed.append(dict(path=p,preflight_sha256=h,actual_sha256=sha(p)))
expected={str(root/'target/release/examples/native_policy_worker'),str(root/'target/release/examples/native_rules_probe')};assert {r['path'] for r in changed}==expected
assert sha(root/'target/release/examples/native_policy_worker')==meta['policy_binary_sha256']
assert meta['model_sha256']==plan['champion']['model_sha256'] and meta['master']==plan['master'] and meta['games']==2000 and meta['iterations']==128 and meta['search']=='gumbel'
for shard in meta['shard_metadata']:
 for field in ['policy_binary_sha256','model_sha256','external_config','upstream_revision','upstream_checkpoint_sha256','source_sha256','source_id','search_profile','gumbel_config']:assert shard[field]==meta[field],field
assert summary['statuses']=={'complete':2000} and summary['incomplete_games']==0 and summary['pairing_verified']
replay=json.loads((out/'replay.json').read_text());assert replay['checked_games']==2000 and replay['raw_sha256']==summary['raw_sha256']
assert json.loads((out/'post-build-differential.json').read_text())['branch_successors']==312879
assert 'Ran 8 tests' in (out/'post-build-python-tests.log').read_text() and (out/'post-build-python-tests.log').read_text().rstrip().endswith('OK')
frozen=root/'local/research/e92/frozen';frozen.mkdir(exist_ok=True)
for name in ['native_policy_worker','native_rules_probe','strength_worker']:shutil.copy2(root/'target/release/examples'/name,frozen/name)
r=dict(scope='All inputs/settings unchanged except two preflight worker hashes after cargo test rebuilt examples before arena startup; all eight actual arena shards use one identical post-test policy build',changed_preflight_binaries=changed,actual_policy_sha256=meta['policy_binary_sha256'],source_model_upstream_settings_unchanged=True,all_shard_builds_match=True,completed=2000,replay_transitions=replay['checked_transitions'],post_build_native_tests=8,post_build_differential_branches=312879,interpretation='Post-run guard failure retained. Actual benchmark endpoint is the post-test build identified in metadata; preflight binary hashes are not the arena build. No policy/outcome changes or rerun.',raw_sha256=summary['raw_sha256'])
(out/'completion-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
