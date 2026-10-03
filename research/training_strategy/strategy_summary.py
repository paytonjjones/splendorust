"""Study-specific record and cost evidence; its module name avoids import collisions."""
import argparse
import json
import sys
from pathlib import Path
from data import ROOT, sha
sys.path.insert(0, str(ROOT/'scripts'))
from collect_evidence import validate_report, record_interval


def canonical(path):
    path=Path(path)
    report=json.loads(path.read_text())
    validate_report(report)
    interval=record_interval(report['records'],report['players'],0)
    credit=0.0
    for game in report['records']:
        if game['status']!='complete':continue
        seat=game['seats'].index(0)
        if game['winners'] & (1<<seat):credit+=1/game['winners'].bit_count()
    missing=report['incomplete_games']
    count=report['requested_games']
    return dict(path=str(path),sha256=sha(path),games=count,completed=report['completed_games'],
        incomplete=missing,credit_bounds=[credit/count,(credit+missing)/count],ci95=interval,
        source_id=report['source_id'],runtime_seconds=report['runtime_seconds'],
        decisions_per_second=report['decisions_per_second'],seed=report['seed'],
        strict_benefit=missing==0 and interval[0]>.51,
        record_set_sha256=__import__('hashlib').sha256(json.dumps(report['records'],sort_keys=True,separators=(',',':')).encode()).hexdigest())


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('directory',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    out=args.directory.resolve()
    result=dict(schema='training-strategy-evidence-summary-v1',directory=str(out),
        complete=(out/'complete.json').exists(),screens={},fits={},data={},
        limits=['Fixed search settings are not equal total training cost.',
                'Shared-host wall time is not an isolated speed measurement.',
                'Incomplete outcomes remain unknown and block strict benefit.',
                'No automatic champion update; no external ranking from canonical internal games.'])
    for path in sorted(out.glob('*/screen.json')):
        result['screens'][path.parent.name]=canonical(path)
    for path in sorted(out.glob('*/manifest.json')):
        fit=json.loads(path.read_text())
        if 'plan' not in fit or 'history' not in fit:continue
        assert sha(path.parent/'model.pt')==fit['checkpoint_sha256']
        assert sha(path.parent/'runtime.pt')==fit['runtime_sha256']
        selected=next(e for e in fit['history'] if e['epoch']==fit['best_epoch'])
        result['fits'][path.parent.name]=dict(checkpoint_sha256=fit['checkpoint_sha256'],
            runtime_sha256=fit['runtime_sha256'],selected_epoch=fit['best_epoch'],
            metrics=selected,seconds=fit['seconds'],plan=fit['plan'])
    for path in sorted(out.glob('*/data.json')):
        receipt=json.loads(path.read_text())
        for field in ('source','inputs'):
            assert sha(receipt[field])==receipt[field+'_sha256']
        receipt['collection']=json.loads(path.with_name('complete.json').read_text())
        receipt['simulation_rate']=receipt['collection']['simulations']/receipt['collection']['seconds']
        receipt['inference_rate']=receipt['collection']['inferences']/receipt['collection']['seconds']
        result['data'][path.parent.name]=receipt
    collection=sum(v['collection']['seconds'] for k,v in result['data'].items() if not k.startswith('scaling-'))
    for name,fit in result['fits'].items():
        screen=result['screens'].get('screen-'+name)
        if screen:
            seconds=collection+fit['seconds']
            delta=[100*(x-.5) for x in screen['credit_bounds']]
            fit['shared_collection_plus_fit_seconds']=seconds
            fit['credit_gain_percentage_points_vs_parent_bounds']=delta
            fit['gain_percentage_points_per_compute_hour_bounds']=[x/(seconds/3600) for x in delta]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(complete=result['complete'],screens=len(result['screens']),
        fits=len(result['fits']),data_sets=list(result['data']))))


if __name__=='__main__':main()
