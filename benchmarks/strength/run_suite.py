#!/usr/bin/env python3
"""Run the frozen screen/confirmation schedules. No policy tuning."""
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
a.output_dir.mkdir(parents=True,exist_ok=True)
if any(a.output_dir.iterdir()):p.error('use a new empty output directory')
schedules=[('alphazero',2,20,1951000,'screen'),('alphazero',3,21,1952000,'screen'),('alphazero',4,20,1953000,'screen'),
 ('alphazero',2,400,2051000,'confirmation'),('alphazero',3,120,2052000,'confirmation'),('alphazero',4,120,2053000,'confirmation'),
 ('seal256',2,20,1954000,'screen'),('seal256',2,200,2054000,'confirmation'),
 ('strong',2,200,1955000,'screen'),('strong',2,1000,2055000,'confirmation'),('random',2,200,2056000,'confirmation')]
for external,players,games,seed,stage in schedules:
    path=a.output_dir/f'{external}-{players}-{stage}.jsonl'
    command=[sys.executable,str(ROOT/'benchmarks/strength/run.py'),'--external',external,'--players',str(players),'--games',str(games),
             '--seed',str(seed),'--stage',stage,'--output',str(path)]
    if external=='seal256':command+=['--external-iterations','500']
    subprocess.run(command,cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'benchmarks/strength/summarize.py'),str(path),'--output',str(path.with_suffix('.summary.json'))],check=True)
native=a.output_dir/'seal256-native-confirmation.jsonl'
subprocess.run([str(ROOT/'local/strength/seal256-native-strength'),'--games','400','--iterations','2000','--seed','3060000','--output',str(native)],check=True)
subprocess.run([sys.executable,str(ROOT/'benchmarks/strength/summarize.py'),str(native),'--output',str(native.with_suffix('.summary.json'))],check=True)
subprocess.run([str(ROOT/'local/strength/inference/bin/python'),str(ROOT/'benchmarks/adapters/schuber6_strength.py'),
                '--root',str(ROOT/'local/strength/external/schuber6'),'--output',str(a.output_dir/'schuber6-integration.json')],check=True)
