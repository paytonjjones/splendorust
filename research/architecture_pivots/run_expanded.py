"""Prepare and train matched expanded-data models after checked collection."""
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from train import prepare

def main():
    out=HERE/'expanded-run';out.mkdir(exist_ok=True)
    required=[HERE/'expansion/complete.json',HERE/'canonical-expansion/complete.json']
    (out/'plan.json').write_text(json.dumps(dict(training_kinds=['small','small-cold','capacity','entity'],epochs=12,batch=512,data='expanded fixed train; original fixed dev',initialization='E81 for warm small; fixed-seed scratch for cold small and large models',history='Prepare public prefixes and ground-truth targets; choose history parent after expanded fit/strength evidence'),indent=2)+'\n')
    while not all(path.exists() for path in required):time.sleep(30)
    def run(name,command):
        with (out/f'{name}.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        (out/'progress.json').write_text(json.dumps(dict(last_completed=name))+'\n')
    run('history-data',[sys.executable,str(HERE/'history_data.py'),'--split','train','--directory',str(ROOT/'local/research/architecture-pivots/expansion/train'),'--prefix','expanded-native'])
    data=prepare('expanded')
    assert data['setup_counts']['train']==30000
    run('history-validation',[sys.executable,str(HERE/'validate_history.py'),'--expanded'])
    run('data-summary',[sys.executable,str(HERE/'data_summary.py'),'--expanded'])
    # Avoid overlap between two training jobs on the GPU.
    control=HERE/'auxiliary-only/manifest.json'
    while True:
        try:
            report=json.loads(control.read_text())
            if len(report['history'])==report['epochs']:break
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(30)
    for kind in ('small','small-cold','capacity','entity'):
        run(f'train-{kind}',[sys.executable,str(HERE/'train.py'),'--kind',kind,'--output',str(HERE/f'expanded-{kind}'),'--data-scale','expanded','--device','mps','--fast-entities'])
    (out/'complete.json').write_text(json.dumps(dict(kinds=['small','small-cold','capacity','entity'],all_epochs_complete=True))+'\n')

if __name__=='__main__':main()
