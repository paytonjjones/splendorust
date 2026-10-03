"""Complete the initial history/auxiliary factorial control without GPU overlap."""
import json
import subprocess
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def main():
    control=HERE/'history-only/manifest.json'
    while True:
        try:
            m=json.loads(control.read_text())
            if len(m['history'])==m['epochs']:break
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(30)
    with (HERE/'auxiliary-only-training.log').open('w') as log:
        subprocess.run([sys.executable,str(HERE/'train.py'),'--kind','history','--parent',str(HERE/'entity/model.pt'),'--history-ablation','no-history','--output',str(HERE/'auxiliary-only'),'--device','mps','--fast-entities'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
if __name__=='__main__':main()
