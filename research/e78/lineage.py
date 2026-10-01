"""Exploratory lineage selection; never a statistical champion promotion."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_evidence import validate_report,record_interval

def provisional_decision(report,margin=0.005):
    validate_report(report)
    if report['players']!=2 or report.get('reproducible') is not True:
        raise ValueError('provisional selection requires fixed-budget two-player evidence')
    credit=0.0
    for game in report['records']:
        if game['status']=='complete':
            seat=game['seats'].index(0)
            if game['winners']&(1<<seat):credit+=1/game['winners'].bit_count()
    lower=credit/report['requested_games']
    upper=(credit+report['incomplete_games'])/report['requested_games']
    return dict(selected=lower>0.5+margin,requested_credit_bounds=[lower,upper],
        ci95=record_interval(report['records'],2,0),margin=margin,
        status='provisional exploration only; no statistical promotion',
        missing_outcome_rule='unknown; worst-case zero for selection; never a declared loss/win')
