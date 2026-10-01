#!/usr/bin/env python3
"""Restartable native self-play -> PyTorch -> native parity -> arena selection loop."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from flywheel_model import sha
ROOT=Path(__file__).resolve().parents[1]

def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cycles',type=int,default=1)
    p.add_argument('--seed',type=int,default=800000000)
    p.add_argument('--games',type=int,nargs='+',default=[5000])
    p.add_argument('--dev-games',type=int,default=1000)
    p.add_argument('--shard-games',type=int,default=1000)
    p.add_argument('--iterations',type=int,default=128)
    p.add_argument('--teacher-iterations',type=int)
    p.add_argument('--search-agent',choices=['puct','gumbel'],default='puct')
    p.add_argument('--teacher-agent',choices=['flywheel-best','flywheel-gumbel','flywheel-gumbel-noisy'],default='flywheel-best')
    p.add_argument('--actor-agent',choices=['flywheel-best','flywheel-gumbel','flywheel-gumbel-noisy'])
    p.add_argument('--actor-iterations',type=int,help='separate student actor budget; teacher iterations label its visited states')
    p.add_argument('--dev-teacher-iterations',type=int)
    p.add_argument('--teacher-model',type=Path,default=Path('research/e30/model.bin'))
    p.add_argument('--teacher-checkpoint',type=Path)
    p.add_argument('--epochs',type=int,default=10)
    p.add_argument('--architecture',choices=['bootstrap','gated','split-bootstrap','residual'],default='bootstrap')
    p.add_argument('--selection',choices=['outcome','teacher','distillation'],default='outcome')
    p.add_argument('--learning-rate',type=float)
    p.add_argument('--public-context',action='store_true')
    p.add_argument('--bitplanes',action='store_true')
    p.add_argument('--distill-incumbent',action='store_true')
    p.add_argument('--trunk-blocks',type=int)
    p.add_argument('--policy-only',action='store_true')
    p.add_argument('--greedy-targets',action='store_true')
    p.add_argument('--encoding-views',type=int,choices=[1,8],default=1)
    p.add_argument('--teacher-replicates',type=int,choices=[1,2,4,8],default=1)
    p.add_argument('--sample-encoding-views',action='store_true')
    p.add_argument('--selection-rule',choices=['strict','provisional'],default='strict')
    p.add_argument('--threads',type=int,default=14)
    p.add_argument('--screen',type=int,default=2000)
    p.add_argument('--confirm',type=int,default=0,help='optional fresh confirmation; 0 keeps the fixed 2k inner-loop gate')
    p.add_argument('--device',default='mps')
    p.add_argument('--target',type=Path,default=Path('local/research/flywheel-target'))
    a=p.parse_args()
    candidate_name="flywheel-gumbel-candidate" if a.search_agent=="gumbel" else "flywheel-candidate"
    baseline_name="flywheel-gumbel" if a.search_agent=="gumbel" else "flywheel-best"
    if a.sample_encoding_views and a.encoding_views!=8:p.error('view sampling requires --encoding-views 8')
    if a.actor_agent and a.actor_iterations is None:p.error('separate actor requires --actor-iterations')
    if a.architecture=='residual' and not a.teacher_checkpoint:p.error('residual requires a learned teacher checkpoint')
    if a.trunk_blocks is not None and a.architecture!='bootstrap':p.error('trunk-blocks requires bootstrap')
    if a.policy_only and (a.architecture!='bootstrap' or a.distill_incumbent):p.error('policy-only requires bootstrap and no distillation')
    if a.bitplanes and a.architecture!='gated':p.error('bitplanes requires a gated student')
    if a.selection=='distillation' and not a.distill_incumbent:p.error('distillation selection requires --distill-incumbent')
    os.chdir(ROOT);a.output=a.output.resolve();a.target=a.target.resolve()
    a.teacher_model=a.teacher_model.resolve()
    if a.teacher_checkpoint: a.teacher_checkpoint=a.teacher_checkpoint.resolve()
    if a.teacher_model.read_bytes()[:8]==b'SPINFO57':a.public_context=True
    if a.public_context and (a.architecture!='bootstrap' or a.policy_only or a.distill_incumbent):p.error('public context requires a full bootstrap student and no incumbent distillation')
    if a.learning_rate is None:a.learning_rate=0.001 if a.architecture=='gated' else 0.0001
    if a.teacher_iterations is None: a.teacher_iterations=a.iterations
    if a.dev_teacher_iterations is None: a.dev_teacher_iterations=a.teacher_iterations
    assert 0<a.teacher_iterations<2**32 and 0<a.dev_teacher_iterations<2**32
    assert a.actor_iterations is None or 0<a.actor_iterations<2**32
    assert 1<=a.cycles<=5 and all(0<g<=100000 for g in a.games)
    assert a.shard_games>0 and a.dev_games>0
    assert a.screen>=2 and a.screen%2==0 and a.confirm>=0 and a.confirm%2==0 and a.threads>0
    a.output.mkdir(parents=True,exist_ok=True)
    plan={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}
    plan.update(initial_teacher_sha256=sha(a.teacher_model),initial_checkpoint_sha256=sha(a.teacher_checkpoint) if a.teacher_checkpoint else None,script_sha256=sha(__file__),
        training_script_sha256=sha(ROOT/'research/train_flywheel.py'),collector_code_sha256=sha(ROOT/'crates/splendor-arena/examples/flywheel_data.rs'),
        model_code_sha256=sha(ROOT/'research/flywheel_model.py'),
        lineage_code_sha256=sha(ROOT/'research/lineage.py'),encoding_views_code_sha256=sha(ROOT/'research/encoding_views.py'),
        split_code_sha256=sha(ROOT/'research/split_model.py') if a.architecture=='split-bootstrap' else None,
        gated_code_sha256=sha(ROOT/'research/gated_model.py') if a.architecture in ['gated','residual'] else None,
        residual_code_sha256=sha(ROOT/'research/residual_model.py') if a.architecture=='residual' else None,
        split_rule='cycle i: train seed+100m*i; dev train+10m; screen train+20m; confirm screen+1b',
        incomplete_rule='strict gate preserved; provisional requested-credit lower point >50.5% or strict CI lower >51%; missing outcomes unknown')
    planpath=a.output/'plan.json'
    if planpath.exists(): assert json.loads(planpath.read_text())==plan,'changed plan; use a new output directory'
    else: atomic(planpath,plan)
    env=os.environ.copy();env['CARGO_TARGET_DIR']=str(a.target)
    def preserve(path):
        if path.exists():
            index=1
            while path.with_name(path.name+f'.attempt-{index:03d}').exists(): index+=1
            path.rename(path.with_name(path.name+f'.attempt-{index:03d}'))
    def run(cmd,log,allowed=(0,)):
        cmd=list(map(str,cmd));start=time.monotonic()
        event={'stage':str(log),'command':cmd,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        print(json.dumps(event),flush=True)
        preserve(log)
        with log.open('w') as f:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        event.update(seconds=time.monotonic()-start,exit_code=result.returncode)
        with (a.output/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        if result.returncode not in allowed: raise RuntimeError(f'failed {log}: exit {result.returncode}')
    binaries=a.target/'release';run(['cargo','build','--release','--locked','--bin','splendor','--example','flywheel_data','--example','transfer_parity'],a.output/'build.log')
    bestpath=a.output/'best.json'
    if not bestpath.exists(): atomic(bestpath,dict(model=str(a.teacher_model),checkpoint=str(a.teacher_checkpoint) if a.teacher_checkpoint else None,model_sha256=sha(a.teacher_model),checkpoint_sha256=sha(a.teacher_checkpoint) if a.teacher_checkpoint else None,status='initial teacher'))
    championpath=a.output/'champion.json'
    champion=dict(model=str(a.teacher_model),checkpoint=str(a.teacher_checkpoint) if a.teacher_checkpoint else None,model_sha256=sha(a.teacher_model),status='fixed reference; provisional lineage cannot replace this file')
    if championpath.exists():assert json.loads(championpath.read_text())==champion
    else:atomic(championpath,champion)
    replay=[]
    for cycle in range(a.cycles):
        c=a.output/f'cycle-{cycle:03d}';c.mkdir(exist_ok=True)
        if (c/'decision.json').exists():
            replay.extend(sorted(p for p in (c/'train').glob('*.bin') if not p.name.endswith(('.views.bin','.context.bin'))));continue
        best=json.loads(bestpath.read_text());assert sha(best['model'])==best['model_sha256']
        if best['checkpoint']:assert sha(best['checkpoint'])==best['checkpoint_sha256']
        env['SPLENDOR_BEST_MODEL']=best['model']
        snapshot=c/'teacher.json'
        if snapshot.exists(): assert json.loads(snapshot.read_text())==best,'teacher changed during unfinished cycle'
        else:atomic(snapshot,best)
        datasets={}
        for split,games,master in [('train',a.games[min(cycle,len(a.games)-1)],a.seed+cycle*100000000),('dev',a.dev_games,a.seed+10000000+cycle*100000000)]:
            folder=c/split;folder.mkdir(exist_ok=True);paths=[]
            for offset in range(0,games,a.shard_games):
                output=folder/f'{offset:06d}.bin';meta=output.with_suffix('.json');receipt=output.with_suffix('.receipt.json')
                if not receipt.exists():
                    preserve(output);preserve(meta);preserve(output.with_suffix('.context.bin'));preserve(output.with_suffix('.views.bin'))
                    run([binaries/'examples/flywheel_data','--games',min(a.shard_games,games-offset),'--seed',master+offset,
                         '--policy-seed',master+offset+3000000000,'--iterations',a.teacher_iterations if split=='train' else a.dev_teacher_iterations,'--depth',16,
                         '--threads',a.threads,'--teacher-agent',a.teacher_agent,*(['--actor-agent',a.actor_agent] if a.actor_agent else []),'--encoding-views',a.encoding_views,'--teacher-replicates',a.teacher_replicates,*([] if a.actor_iterations is None else ['--actor-iterations',a.actor_iterations]),*(['--public-context'] if a.public_context else []),'--output',output],output.with_suffix('.log'))
                    atomic(receipt,dict(data_sha256=sha(output),manifest_sha256=sha(meta),teacher_sha256=best['model_sha256'],views_sha256=sha(output.with_suffix('.views.bin')) if a.encoding_views==8 else None,context_sha256=sha(output.with_suffix('.context.bin')) if a.public_context else None))
                r=json.loads(receipt.read_text())
                if a.public_context:assert sha(output.with_suffix('.context.bin'))==r['context_sha256']
                if a.encoding_views==8:assert sha(output.with_suffix('.views.bin'))==r['views_sha256']
                assert sha(output)==r['data_sha256'] and sha(meta)==r['manifest_sha256'] and r['teacher_sha256']==best['model_sha256']
                paths.append(output)
            datasets[split]=paths
        model=c/'model'
        if not (model/'manifest.json').exists():
            preserve(model)
            command=[sys.executable,ROOT/'research/train_flywheel.py','--train',*replay,*datasets['train'],
                '--dev',*datasets['dev'],'--output',model,'--epochs',a.epochs,'--device',a.device,'--seed',800000007+cycle,
                '--architecture',a.architecture,'--selection',a.selection,'--learning-rate',a.learning_rate]
            if a.trunk_blocks is not None:command+=['--trunk-blocks',a.trunk_blocks]
            # Cross-architecture students start from scratch; same-architecture cycles warm start.
            with Path(best['model']).open('rb') as f:teacher_magic=f.read(8)
            teacher_gated=teacher_magic in [b'SPGATED1',b'SPGATED2']
            teacher_residual=teacher_magic==b'SPRESID1'
            compatible=(a.architecture=='residual' and not teacher_gated and teacher_magic!=b'SPDUAL01') or (not teacher_residual and ((not teacher_gated and a.architecture=='split-bootstrap') or (teacher_magic!=b'SPDUAL01' and teacher_gated==(a.architecture=='gated') and (not teacher_gated or (teacher_magic==b'SPGATED2')==a.bitplanes))))
            if best['checkpoint'] and compatible:
                command+=['--warmstart',best['checkpoint']]
            if a.public_context:command+=['--public-context']
            if a.bitplanes:command+=['--bitplanes']
            if a.policy_only:command+=['--policy-only']
            if a.greedy_targets:command+=['--greedy-targets']
            if a.sample_encoding_views:command+=['--sample-encoding-views']
            if a.distill_incumbent:
                assert best['checkpoint'],'distillation needs the incumbent PyTorch checkpoint'
                command+=['--distill-teacher',best['checkpoint']]
            run(command,c/'training.log')
        m=json.loads((model/'manifest.json').read_text());assert sha(model/'model.bin')==m['model_sha256']
        env['SPLENDOR_CANDIDATE_MODEL']=str(model/'model.bin')
        run([binaries/'examples/transfer_parity',model/'model.bin',model/'parity.json','real'],c/'parity.log')
        split_identity=a.architecture in ['split-bootstrap','residual'] and m['best_epoch']==0 and best['checkpoint'] and m['warmstart_sha256']==sha(best['checkpoint'])
        context_identity=a.public_context and a.architecture=='bootstrap' and a.trunk_blocks is None and m['best_epoch']==0 and best['checkpoint'] and m['warmstart_sha256']==sha(best['checkpoint']) and Path(best['model']).read_bytes()[:8]!=b'SPINFO57'
        if m['model_sha256']==best['model_sha256'] or split_identity or context_identity:
            atomic(c/'decision.json',dict(cycle=cycle,selected=False,reason='unchanged incumbent function; skip arena self-comparison',teacher_sha256=best['model_sha256'],candidate_sha256=m['model_sha256'],best_epoch=m['best_epoch']))
            replay.extend(datasets['train']);continue
        gate=c/'gate';seed=a.seed+20000000+cycle*100000000
        if not (gate/'decision.json').exists():
            preserve(gate)
            run([sys.executable,ROOT/'scripts/promote.py','--candidate',candidate_name,'--baseline',baseline_name,
                '--iterations',a.iterations,'--depth',16,'--screen',a.screen,'--confirm',a.confirm,
                '--seed',seed,'--threads',a.threads,'--output',gate],c/'gate.log',(0,2))
        decision=json.loads((gate/'decision.json').read_text())
        if decision.get('decision')=='reject: execution failure': raise RuntimeError(f'execution failed: {gate}; fix the cause before the next cycle')
        # A blocked screen cannot stop learning. Reserve and measure confirmation
        # if its bounded upper interval still permits benefit. Keep strict rejection.
        sys.path.insert(0,str(ROOT/'scripts'))
        from collect_evidence import validate_report,record_interval
        confirm=gate/'confirm.json'
        if a.confirm and not confirm.exists() and decision.get('decision')=='reject: incomplete games' and (gate/'screen.json').exists():
            screen=json.loads((gate/'screen.json').read_text());validate_report(screen)
            if record_interval(screen['records'],2,0)[1]>=0.51:
                run([binaries/'splendor','compare','--agent-a',candidate_name,'--agent-b',baseline_name,
                     '--games',a.confirm,'--iterations',a.iterations,'--depth',16,'--seed',seed+1000000000,
                     '--threads',a.threads,'--output',confirm],c/'research-confirm.log')
        selected=decision.get('decision')=='promote';bounds=None;provisional=None
        final=confirm if confirm.exists() else gate/'screen.json'
        if final.exists():
            report=json.loads(final.read_text());validate_report(report)
            bounds=record_interval(report['records'],2,0)
            assert report['reproducible'] is True and report['seed']==(seed+1000000000 if final==confirm else seed)
            assert report['run_config']['names']==[candidate_name,baseline_name]
            selected=selected or (decision.get('decision')=='reject: incomplete games' and bounds[0]>0.51)
        if a.selection_rule=='provisional':
            from lineage import provisional_decision
            provisional=provisional_decision(report)
            selected=provisional['selected']
        # Validate checkpoint immutability before a selection becomes current.
        assert sha(best['model'])==best['model_sha256'] and sha(model/'model.bin')==m['model_sha256']
        if selected:
            atomic(bestpath,dict(model=str(model/'model.bin'),checkpoint=str(model/'model.pt'),
                model_sha256=m['model_sha256'],checkpoint_sha256=m['checkpoint_sha256'],status='provisional lineage; no champion promotion' if a.selection_rule=='provisional' else 'strict promotion' if decision['decision']=='promote' else 'research selection; strict incomplete rejection retained',cycle=cycle))
        result=dict(cycle=cycle,selected=selected,search_agent=a.search_agent,selection_rule=a.selection_rule,provisional=provisional,champion_sha256=champion['model_sha256'],strict_decision=decision,
            conservative_selection_interval=bounds,selection_stage=final.stem,teacher_sha256=best['model_sha256'],candidate_sha256=m['model_sha256'],
            best_epoch=m['best_epoch'],train_rows=sum(x['rows'] for x in m['train']),dev_rows=sum(x['rows'] for x in m['dev']))
        atomic(c/'decision.json',result);print(json.dumps(result),flush=True)
        replay.extend(datasets['train'])
    atomic(a.output/'completed.json',dict(cycles=a.cycles,best=json.loads(bestpath.read_text())))
if __name__=='__main__':main()
