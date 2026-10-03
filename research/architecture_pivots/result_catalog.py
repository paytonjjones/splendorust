"""Collect finished and partial trials without turning pending work into results."""
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
from collect_evidence import record_interval,validate_report

def main():
    fit={};strength={};pilots={};failures={}
    for path in sorted(HERE.glob('*/manifest.json')):
        d=json.loads(path.read_text())
        if 'best_epoch' not in d:continue
        best=d['initial'] if d['best_epoch']==0 else next(r for r in d['history'] if r['epoch']==d['best_epoch'])
        fit[path.parent.name]=dict(parameters=d['parameters'],best_epoch=d['best_epoch'],
            finished_epochs=len(d['history']),planned_epochs=d['epochs'],
            complete=len(d['history'])==d['epochs'],training_seconds=d['seconds'],device=d['device'],
            data_scale=d.get('data_scale','initial'),checkpoint_sha256=d['checkpoint_sha256'],
            parent_sha256=d.get('parent_sha256'),history_ablation=d.get('history_ablation'),
            backbone=d.get('backbone','entity' if d['kind']=='history' else d['kind']),
            history_version=d.get('history_version',1 if d['kind']=='history' else 0),selected=best)
        stop_path=path.with_name('early-stop.json')
        if stop_path.exists():
            stop=json.loads(stop_path.read_text())
            assert stop['completed_epochs']==len(d['history'])
            assert stop['planned_epochs']==d['epochs']
            assert stop['selected_epoch']==d['best_epoch']
            assert stop['selected_checkpoint_sha256']==d['checkpoint_sha256']
            assert stop['original_manifest_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            fit[path.parent.name].update(training_status='user-directed early stop',
                early_stop=stop,early_stop_receipt_sha256=hashlib.sha256(stop_path.read_bytes()).hexdigest())
    for path in sorted(HERE.glob('*/decision.json')):
        decision=json.loads(path.read_text())
        if 'raw_report_sha256' not in decision:
            failures[path.parent.name]=decision
            continue
        reports=[p for p in (path.parent/'confirm.json',path.parent/'screen.json') if p.exists()]
        report=next(p for p in reports if hashlib.sha256(p.read_bytes()).hexdigest()==decision['raw_report_sha256'])
        raw=report.read_bytes();d=json.loads(raw);validate_report(d)
        assert hashlib.sha256(raw).hexdigest()==decision['raw_report_sha256']
        assert all(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) for a,b in zip(record_interval(d['records'],2,0),decision['interval_from_records']))
        strength[path.parent.name]=dict(profile='splendorust-v2',master=d['seed'],
            completed=d['completed_games'],incomplete=d['incomplete_games'],
            credit=d['agents'][0]['win_rate'],ci95=d['agents'][0]['ci95'],
            seconds=d['runtime_seconds'],games_per_second=d['games_per_second'],
            decision=decision['decision'],record_set_sha256=decision['record_set_sha256'])
    native_summaries=[*HERE.glob('native-*/summary.json'),*HERE.glob('expanded-native-*/summary.json')]
    for path in sorted(native_summaries):
        d=json.loads(path.read_text());raw=gzip.decompress((path.parent/'records.json.gz').read_bytes())
        records=json.loads(raw);assert len(records)==d['games']
        assert hashlib.sha256(raw).hexdigest()==d['record_set_sha256']
        assert sum(r['status']=='complete' for r in records)==d['completed']
        assert all(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) for a,b in zip(record_interval(records,2,0),d['ci95']))
        target=pilots if d['games']<2000 else strength
        target[path.parent.name]={k:d[k] for k in ('profile','master','games','completed','credit','ci95','seconds',
            'games_per_second','record_set_sha256','iterations','workers','policy_seconds','inferences','simulations')}
    result=dict(fit=fit,strength=strength,excluded_pilots=pilots,failed_gates=failures,
        scope='Finished full strength screens; pilots and failed executions separated; partial fit explicitly marked')
    (HERE/'result-catalog.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(fit_trials=len(fit),finished_strength_runs=len(strength))))

if __name__=='__main__':main()
