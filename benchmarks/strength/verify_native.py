#!/usr/bin/env python3
"""Replay all retained native control actions without running search."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
checked={}
for path in sorted((ROOT/'benchmarks/strength/results').glob('*.jsonl')):
  meta,*rows=map(json.loads,path.read_text().splitlines())
  if meta.get('engine')!='seal256_native':continue
  process=subprocess.Popen([ROOT/'local/strength/seal256-replay'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  assert len(rows)==meta['games']
  for row in rows:
   process.stdin.write(json.dumps(row)+'\n');process.stdin.flush();out=json.loads(process.stdout.readline())
   assert 'error' not in out,(path,row['index'],out)
   assert out['scores']==row['scores'] and out['round']==row['round'] and out['rewards']==row['rewards'],(path,row['index'])
   assert out['terminal']==(row['status'] in ('complete','native_no_winner'))
  checked[path.name]=len(rows)
  process.stdin.close();process.wait();process.stdout.close()
(ROOT/'benchmarks/strength/native-replay-validation.json').write_text(json.dumps({'games':sum(checked.values()),'files':checked,
 'scope':'Every recorded native action passes the unchanged native verifier and apply; scores, rounds, terminal flags and rewards match. Native zero-reward terminals remain no-winner outcomes.'},indent=2)+'\n')
print(sum(checked.values()),'native games replayed')
