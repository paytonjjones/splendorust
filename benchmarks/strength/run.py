#!/usr/bin/env python3
"""Paired strength matches on published rules with native external planning."""
import argparse,hashlib,json,os,platform,select,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

class RPC:
    def __init__(self,command,log):
        self.log=open(log,'w')
        self.process=subprocess.Popen(list(map(str,command)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=self.log,text=True,bufsize=1,cwd=ROOT/'local/strength')
    def receive(self,timeout=180):
        if not select.select([self.process.stdout],[],[],timeout)[0]:raise TimeoutError('external request timeout')
        line=self.process.stdout.readline()
        if not line:raise RuntimeError(f'worker exited: {self.process.poll()}')
        result=json.loads(line)
        if 'error' in result:raise RuntimeError(result['error'])
        return result
    def call(self,op,**payload):
        self.process.stdin.write(json.dumps(dict(op=op,**payload))+'\n');self.process.stdin.flush()
        return self.receive()
    def close(self):
        self.process.terminate()
        try:self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process.stdin.close();self.process.stdout.close();self.log.close()

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(args):
    args.output.parent.mkdir(parents=True,exist_ok=True)
    core=RPC([ROOT/'target/release/examples/strength_worker'],str(args.output)+'.core.log')
    data=core.call('data');ext=None
    command=[];ready=None
    if args.external=='alphazero':
        command=[ROOT/'local/strength/inference/bin/python',ROOT/'benchmarks/adapters/alphazero_strength.py',
                 '--root',args.source,'--players',args.players,'--simulations',args.external_iterations]
        ext=RPC(command,str(args.output)+'.external.log')
        try:ready=ext.receive()
        except Exception:
            ext.close();core.close();raise
    elif args.external=='seal256':
        command=[ROOT/'local/strength/seal256-adapter',args.external_iterations]
        ext=RPC(command,str(args.output)+'.external.log')
    if ext: ext.call('data',cards=data['cards'],nobles=data['nobles'])
    metadata={'schema_version':1,'ruleset':'published-base-v1','planning_profile':'published-base-native-planning-v1',
        'observation_profile':'public-observation-sampled-hidden-v1','players':args.players,'games':args.games,
        'seed':args.seed,'policy_seed':args.policy_seed,'sampling_seed':args.sampling_seed,'candidate':args.candidate,'external':args.external,'stage':args.stage,
        'search_iterations':args.iterations,'external_iterations':args.external_iterations,
        'wall_budget_seconds':None,'decision_cap':args.cap,'source_id':data['source_id'],'engine':data['engine'],
        'splendorust_revision':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        'core_binary_sha256':sha(ROOT/'target/release/examples/strength_worker'),
        'external_command':list(map(str,command)),'external_config':ready,
        'host':platform.platform(),'python':platform.python_version(),'reproduction_command':args.reproduction,
        'harness_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'benchmarks/adapters/alphazero_strength.py',ROOT/'benchmarks/adapters/seal256_strength.cpp',ROOT/'crates/splendor-arena/examples/strength_worker.rs']},
        'limits':'Native planning rules differ from actual transitions. Unsupported actions stop a game. Iteration counts are not equal compute. RPC and conversion time are included.'}
    with args.output.open('w') as out:
        out.write(json.dumps(metadata)+'\n');out.flush()
        try:
            for index in range(args.games):
                block=index//args.players;rotation=index%args.players
                identities=[args.candidate]+[args.external]*(args.players-1)
                seats=identities[rotation:]+identities[:rotation]
                seed=args.seed+block;agent_seed=args.policy_seed+block
                core.call('reset',players=args.players,seed=seed,sampling_seed=args.sampling_seed+block,
                          agent_seed=agent_seed,agent_seeds=[agent_seed+((i+rotation)%args.players) for i in range(args.players)],iterations=args.iterations,seats=seats)
                if ext:ext.call('reset',seed=agent_seed)
                record={'index':index,'block':block,'rotation':rotation,'setup_seed':seed,'seats':seats,
                        'status':'decision_limit','actions':[],'native_actions':[],'rewards':None,'reason':None,
                        'policy_seconds':[0.]*args.players}
                started=time.perf_counter();pending=None
                try:
                    for decision in range(args.cap):
                        state=core.call('observe');o=state['observation'];current=o['current']
                        if state['outcome'] is not None:
                            winners=state['outcome']['winners'];num=winners.bit_count()
                            record.update(status='complete',rewards=[1/num if winners&(1<<i) else 0 for i in range(args.players)])
                            break
                        if not state['legal']:
                            record.update(status='no_legal_action',reason='published rules have no action');break
                        tick=time.perf_counter()
                        if seats[current] not in ('alphazero','seal256'):
                            action=core.call('select')['action']
                        elif o['phase']=='Main':
                            result=ext.call('choose',observation=core.call('sample'),seed=(agent_seed+decision)%2**32)
                            record['native_actions'].append(result.get('native_action'))
                            if result.get('unsupported'):
                                record.update(status='unsupported',reason=result['unsupported']);break
                            action=result['action']
                            if action not in state['legal']:
                                record.update(status='unsupported',reason='native action outside published legal set',attempted_action=action);break
                            if action[0] in (3,4):
                                id=o['market'][action[1]] if action[0]==3 else o['players'][current]['reserved'][action[1]]['card']
                                c=data['cards'][id];p=o['players'][current]
                                pending=[5]+[min(max(cost-bonus,0),token) for cost,bonus,token in zip(c['cost'],p['bonuses'],p['tokens'])]+[0]
                        elif o['phase'].startswith('Payment'):
                            action=pending
                        elif o['phase']=='Noble' and len(state['legal'])==1:
                            action=state['legal'][0]
                        else:
                            record.update(status='unsupported',reason='native policy has no canonical '+o['phase']+' choice');break
                        record['policy_seconds'][current]+=time.perf_counter()-tick
                        if action not in state['legal']:
                            record.update(status='invalid',reason='invalid translated subphase',attempted_action=action);break
                        core.call('apply',action=action);record['actions'].append(action)
                    else:
                        # A final transition at the cap can still be a normal completion.
                        state=core.call('observe')
                        if state['outcome'] is not None:
                            winners=state['outcome']['winners'];num=winners.bit_count()
                            record.update(status='complete',rewards=[1/num if winners&(1<<i) else 0 for i in range(args.players)])
                except TimeoutError as e:record.update(status='capped',reason=str(e))
                except Exception as e:record.update(status='invalid',reason=str(e))
                final=core.call('observe')['observation']
                record.update(scores=[p['score'] for p in final['players']],turns=final['turns'],decisions=len(record['actions']),
                              elapsed_seconds=time.perf_counter()-started)
                out.write(json.dumps(record)+'\n');out.flush()
                print(f'{index+1}/{args.games} {record["status"]}: {record["scores"]}',flush=True)
                if record['status'] in ('invalid','capped'):
                    # A crashed worker requires a fresh process. Retain the failure; do not fabricate the remaining schedule.
                    if ext:
                        ext.close();ext=RPC(command,str(args.output)+f'.external-restart-{index}.log')
                        if args.external=='alphazero':ext.receive()
                        ext.call('data',cards=data['cards'],nobles=data['nobles'])
        finally:
            core.close()
            if ext:ext.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--external',choices=['alphazero','seal256','random','strong'],required=True)
    p.add_argument('--source',type=Path,default=ROOT/'local/strength/external/alphazero')
    p.add_argument('--candidate',choices=['search','strong','random','learned','learned-cycle'],default='search')
    p.add_argument('--players',type=int,choices=[2,3,4],default=2);p.add_argument('--games',type=int,required=True)
    p.add_argument('--iterations',type=int,default=128);p.add_argument('--external-iterations',type=int,default=0)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--policy-seed',type=int,default=2500001);p.add_argument('--sampling-seed',type=int,default=3500001);p.add_argument('--cap',type=int,default=2000)
    p.add_argument('--stage',choices=['smoke','screen','confirmation'],default='screen');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.source=a.source.resolve();a.output=a.output.resolve();a.reproduction='python3 benchmarks/strength/run.py '+' '.join(sys_argv for sys_argv in __import__('sys').argv[1:])
    if a.games<=0 or a.games%a.players:p.error('games must be positive and divisible by players')
    if a.external=='seal256' and a.external_iterations<=1:p.error('seal256 requires at least two iterations')
    run(a)
