"""Validate the separately preregistered fixed E49 confirmation; retain screen evidence."""
import hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from promote import decision,validate_stage,checked_interval
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
gate=Path(__file__).parent/'gate'
args=SimpleNamespace(**json.loads((gate/'run.json').read_text()))
screen=json.loads((gate/'screen.json').read_text());path=gate/'confirm.json';raw=path.read_bytes();report=json.loads(raw)
source=validate_stage(screen,args,2000,1240000000,None)
validate_stage(report,args,5000,2240000000,source)
interval=checked_interval(report,2)
model=ROOT/'research/e49/model/model.bin';teacher=ROOT/'research/e41/cycle-0/model/model.bin'
assert sha(model)=='cde5849353068e7b11a583a39fe38a36d8499886ed5f6ee84ec6fb55c41b9a07'
assert sha(teacher)=='d355838dd48742c39e2e51f092586c23616d974e413521fc056b0ceab7d00600'
strict=decision(report,2,0.01,0)
result=dict(decision=strict,selected=strict=='promote' or (strict=='reject: incomplete games' and interval[0]>0.51),
    stage='fresh fixed confirmation',source_id=report['source_id'],games=report['requested_games'],complete=report['completed_games'],
    interval_from_records=interval,conditional_credit=report['agents'][0]['win_share']/report['completed_games'],
    candidate_sha256=sha(model),teacher_sha256=sha(teacher),raw_report_sha256=sha(path),
    record_set_sha256=hashlib.sha256(json.dumps(report['records'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
    validator_sha256=sha(Path(__file__)),seconds=report['runtime_seconds'],
    evidence_tools_sha256={name:sha(ROOT/'scripts'/name) for name in ['promote.py','collect_evidence.py']})
(gate/'confirmation-decision.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
