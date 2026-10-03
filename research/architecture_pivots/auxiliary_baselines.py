"""Train-only action/card marginal baselines with legal public belief support."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from history_data import AUX,CARDS,ROOT

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--expanded',action='store_true');args=ap.parse_args()
    local=ROOT/'local/research/architecture-pivots'
    registry=local/('expanded-data.json' if args.expanded else 'data.json')
    data=json.loads(registry.read_text());stats={}
    tiers=np.array([int(c['tier']) for c in CARDS])
    def arrays(split,index,e):
        base=Path(e.get('aux_base',local/f'{split}-{index:02d}'))
        return np.memmap(str(base)+'.aux.bin',mode='r',dtype=AUX,shape=(e['rows'],)),base
    for native in (True,False):
        op=np.ones(81);belief=np.ones(90)
        for index,e in enumerate(data['train']):
            if e['native']!=native:continue
            a,_=arrays('train',index,e)
            targets=a['opponent'];op+=np.bincount(targets[targets>=0],minlength=81)
            targets=a['belief'].reshape(-1);belief+=np.bincount(targets[targets>=0],minlength=90)
        op/=op.sum();op_ce=op_correct=op_count=hidden_ce=hidden_correct=hidden_count=uniform_ce=0
        for index,e in enumerate(data['dev']):
            if e['native']!=native:continue
            a,base=arrays('dev',index,e);target=a['opponent'];target=target[target>=0]
            op_ce-=np.log(op[target]).sum();op_correct+=(target==op.argmax()).sum();op_count+=len(target)
            pool=np.memmap(str(base)+'.pool.bin',mode='r',dtype='<f4',shape=(e['rows'],90))
            x=np.memmap(e['inputs'],mode='r',dtype='<f4',shape=(e['rows'],525))
            for slot in range(3):
                valid=a['belief'][:,slot]>=0;target=a['belief'][valid,slot]
                row_tier=np.rint(x[valid,515+slot]*3).astype(int)
                allowed=(pool[valid]>0)&(tiers[None,:]==row_tier[:,None])
                assert np.all(allowed[np.arange(len(target)),target])
                prob=allowed*belief[None,:];prob/=prob.sum(-1,keepdims=True)
                hidden_ce-=np.log(prob[np.arange(len(target)),target]).sum()
                hidden_correct+=(prob.argmax(-1)==target).sum();hidden_count+=len(target)
                uniform_ce+=np.log(allowed.sum(-1)).sum()
        stats['native' if native else 'canonical']=dict(opponent_ce=op_ce/op_count,
            opponent_accuracy=op_correct/op_count,opponent_targets=op_count,most_common_action=int(op.argmax()),
            hidden_ce=hidden_ce/hidden_count,hidden_accuracy=hidden_correct/hidden_count,
            hidden_uniform_ce=uniform_ce/hidden_count,hidden_targets=hidden_count)
    out=Path(__file__).parent/('expanded-auxiliary-baselines.json' if args.expanded else 'auxiliary-baselines.json')
    out.write_text(json.dumps(dict(registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),
        scope='Separate profile marginals from train labels only; reservation support from public pool/tier only',
        add_one_smoothing=True,results=stats),indent=2)+'\n');print(out.read_text())

if __name__=='__main__':main()
