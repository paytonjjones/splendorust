#!/usr/bin/env python3
"""Measure a learning iteration from saved data, stage events and arena records."""
import argparse,collections,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_evidence import validate_report,record_interval

def relative_elo(p):
    return 400*math.log10(p/(1-p)) if 0<p<1 else None

def assess(cycle):
    generation={}
    for split in ['train','dev']:
        manifests=[json.loads(p.read_text()) for p in sorted((cycle/split).glob('*.json')) if not p.name.endswith('.receipt.json')]
        if not manifests:raise ValueError(f'missing {split} data')
        for m in manifests:
            if m['games']!=m['complete']+m['blocked']+m['capped']:raise ValueError('invalid generation counts')
        games=sum(m['games'] for m in manifests);rows=sum(m['rows'] for m in manifests);seconds=sum(m['seconds'] for m in manifests)
        generation[split]=dict(games=games,positions=rows,seconds=seconds,games_per_second=games/seconds,
            positions_per_second=rows/seconds,complete=sum(m['complete'] for m in manifests),
            blocked=sum(m['blocked'] for m in manifests),capped=sum(m['capped'] for m in manifests),
            teacher_simulations=sorted({m['iterations'] for m in manifests}),
            simulations=sum(m['simulations'] for m in manifests),inference_calls=sum(m['inference_calls'] for m in manifests))
    model=json.loads((cycle/'model/manifest.json').read_text())
    arena={};evaluation_seconds=0
    for stage in ['screen','confirm']:
        path=cycle/'gate'/f'{stage}.json'
        if not path.exists():continue
        r=json.loads(path.read_text());validate_report(r);ci=record_interval(r['records'],2,0)
        credit=r['agents'][0]['win_share'];complete=r['completed_games'];p=credit/complete if complete else None
        evaluation_seconds+=r['runtime_seconds']
        arena[stage]=dict(games=r['requested_games'],complete=complete,statuses=dict(collections.Counter(x['status'] for x in r['records'])),
            credit=credit,conditional_rate=p,conservative_ci95=ci,relative_elo_point=relative_elo(p) if p is not None else None,
            relative_elo_ci95=[relative_elo(x) for x in ci],seconds=r['runtime_seconds'],source=r['source_id'],
            simulation_budget=r['run_config']['search']['iterations'],reproducible=r['reproducible'])
    measured=sum(x['seconds'] for x in generation.values())+model['seconds']+evaluation_seconds
    decision=cycle/'gate/decision.json';plan=cycle.parent/'plan.json'
    begin=plan if cycle.name=='cycle-000' else cycle/'teacher.json'
    wall=decision.stat().st_mtime-begin.stat().st_mtime if decision.exists() else None
    final=arena.get('confirm',arena.get('screen'));games=sum(x['games'] for x in generation.values());positions=sum(x['positions'] for x in generation.values())
    return dict(cycle=str(cycle),generation=generation,training_seconds=model['seconds'],best_epoch=model['best_epoch'],
        candidate_sha256=model['model_sha256'],arena=arena,strict_decision=json.loads(decision.read_text()) if decision.exists() else None,
        confirmed='confirm' in arena,selection_stage='confirm' if 'confirm' in arena else 'screen',measured_stage_seconds=measured,end_to_end_wall_seconds=wall,
        generated_games_per_end_to_end_second=games/wall if wall and final else None,
        positions_per_end_to_end_second=positions/wall if wall and final else None,
        conditional_relative_elo_per_end_to_end_hour=final['relative_elo_point']/(wall/3600) if wall and final and final['relative_elo_point'] is not None else None,
        interpretation='Elo conversion is conditional on this opponent and compute budget. Missing outcomes bounded in interval. Screen gain is provisional. Full wall time includes checks, startup, collection, training and arena; measured stage sum excludes overhead. No global Elo or compounding claim from one cycle.')

def main():
    p=argparse.ArgumentParser();p.add_argument('cycle',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(assess(a.cycle),indent=2)+'\n')
if __name__=='__main__':main()
