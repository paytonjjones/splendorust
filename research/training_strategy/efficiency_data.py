"""Join ordered collector chunks without changing row or terminal-label bytes."""
import json
import shutil
from pathlib import Path

from audit_targets import audit
from data import prepare, read, sha, validate


def assemble(parts, output):
    parts = [Path(path).resolve() for path in parts]
    output = Path(output).resolve()
    assert parts and len(set(parts)) == len(parts)
    checks = []
    for path in parts:
        validate(read(path / 'rows.bin'))
        checks.append(dict(row_sha256=sha(path / 'rows.bin'),
                           history_sha256=sha(path / 'histories.jsonl')))
    receipts = [json.loads((path / 'complete.json').read_text()) for path in parts]
    fields = ('cheap_iterations', 'depth', 'engine', 'full_probability', 'iterations',
              'row_bytes', 'stochastic_turns', 'threads', 'world_pool')
    for receipt in receipts:
        assert all(receipt[key] == receipts[0][key] for key in fields)
        assert receipt['all_games_replayed'] is True
    records = []
    setups = set()
    for path, receipt in zip(parts, receipts):
        lines = (path / 'histories.jsonl').read_text().splitlines()
        assert len(lines) == receipt['games']
        for local_game, line in enumerate(lines):
            record = json.loads(line)
            assert record['game'] == local_game
            seed = record['history']['seed']
            assert seed not in setups, 'Collector chunks share setup IDs'
            setups.add(seed)
            record['game'] = len(records)
            records.append(record)
    assert len(records) == sum(receipt['games'] for receipt in receipts)
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'rows.bin').open('xb') as target:
        for path in parts:
            with (path / 'rows.bin').open('rb') as source:
                shutil.copyfileobj(source, target, 4 << 20)
    with (output / 'histories.jsonl').open('x') as target:
        for record in records:
            target.write(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n')
    completion = {key: receipts[0][key] for key in fields}
    completion.update(all_games_replayed=True,
                      counts=[sum(receipt['counts'][i] for receipt in receipts) for i in range(3)])
    for key in ('games', 'rows', 'full_rows', 'simulations', 'inferences', 'seconds'):
        completion[key] = sum(receipt[key] for receipt in receipts)
    completion.update(seed=receipts[0]['seed'], policy_seed=receipts[0]['policy_seed'],
                      chunked=True, parts=[dict(directory=str(path),
                      completion_sha256=sha(path / 'complete.json'),
                      row_sha256=check['row_sha256'],
                      history_sha256=check['history_sha256'])
                      for path, check in zip(parts, checks)])
    (output / 'complete.json').write_text(json.dumps(completion, indent=2) + '\n')
    try:
        prepare(output)
        result = audit(output)
        assert result['terminal_labels_match_records']
    except BaseException:
        (output / 'complete.json').rename(output / 'invalid-completion.json')
        raise
    (output / 'target-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return completion
