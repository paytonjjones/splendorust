"""Retain a separate P2.1 decision for every finished canonical architecture gate."""
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from reassess_promotion import reassess


def main():
    out=HERE/'reanalysis';out.mkdir(exist_ok=True)
    entries={};failures={}
    for old in sorted(HERE.parent.glob('*/decision.json')):
        decision=json.loads(old.read_text())
        if 'raw_report_sha256' not in decision:
            failures[old.parent.name]=dict(original_decision=decision,reason='No valid finished strength report')
            continue
        result=reassess(old.parent)
        path=out/f'{old.parent.name}.json'
        if path.exists():
            assert json.loads(path.read_text())==result,'Existing reassessment differs; preserve it and use a new policy directory'
        else:
            with path.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
        entries[old.parent.name]=dict(original_decision=result['original_decision'],decision=result['decision'],
            interval_from_records=result['interval_from_records'],completion=result['completion'],
            raw_report_sha256=result['raw_report_sha256'],path=str(path))
    # The index can add newly finished gates; individual reassessments are immutable.
    (HERE/'reanalysis-index.json').write_text(json.dumps(dict(policy='bounded-no-action-v2.1',
        analyses=entries,execution_failures_not_reassessed=failures),indent=2)+'\n')
    print(json.dumps(dict(reassessed=len(entries),changed=[name for name,r in entries.items()
        if r['original_decision']!=r['decision']])))


if __name__=='__main__':main()
