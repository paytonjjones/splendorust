"""Frozen-checkpoint diagnostics; bootstrap independent setups, not positions.

This does not select weights, tune search, or change the registered strength
tests. Ground-truth labels enter scoring only, after public-input inference.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import torch
from models import ROOT, load
from history_data import AUX, CARDS
from flywheel_model import DTYPE, sha

HERE = Path(__file__).resolve().parent


def bootstrap(blocks, repeats, seed):
    values = np.asarray(list(blocks.values()), dtype=np.float64)
    # sums: opponent model-minus-frequency CE/count,
    # hidden model-minus-uniform CE/count, hidden model-minus-frequency CE.
    rng = np.random.default_rng(seed)
    samples = []
    for offset in range(0, repeats, 256):
        ix = rng.integers(len(values), size=(min(256, repeats-offset), len(values)))
        totals = values[ix].sum(1)
        samples.append(np.column_stack((totals[:,0]/totals[:,1],
                                       totals[:,2]/totals[:,3], totals[:,4]/totals[:,3])))
    samples = np.concatenate(samples)
    total = values.sum(0)
    means = [total[0]/total[1], total[2]/total[3], total[4]/total[3]]
    names = ('opponent_ce_minus_frequency', 'hidden_ce_minus_uniform', 'hidden_ce_minus_frequency')
    return {name: dict(mean=means[i], ci95=np.quantile(samples[:,i],[.025,.975]).tolist())
            for i,name in enumerate(names)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, default=HERE/'expanded-history/model.pt')
    parser.add_argument('--output', type=Path, default=HERE/'expanded-history/auxiliary-diagnostics.json')
    parser.add_argument('--batch', type=int, default=128)
    parser.add_argument('--bootstrap-repeats', type=int, default=10000)
    args = parser.parse_args()
    assert not args.output.exists(), 'Keep previous diagnostic evidence'
    started = time.monotonic()
    torch.set_num_threads(2)
    model, payload = load(args.checkpoint, 'cpu')
    assert payload['kind']=='history' and payload['history_version']==2
    local=ROOT/'local/research/architecture-pivots'
    registry=local/'expanded-data.json'
    data=json.loads(registry.read_text())
    tiers=np.array([int(card['tier']) for card in CARDS])
    baseline=json.loads((HERE/'expanded-auxiliary-baselines.json').read_text())
    assert baseline['registry_sha256']==sha(registry)
    counts={native:[np.ones(81),np.ones(90)] for native in (True,False)}
    for index,entry in enumerate(data['train']):
        base=Path(entry.get('aux_base',local/f'train-{index:02d}'))
        aux=np.memmap(str(base)+'.aux.bin',mode='r',dtype=AUX,shape=(entry['rows'],))
        op,belief=counts[entry['native']]
        target=aux['opponent'];op+=np.bincount(target[target>=0],minlength=81)
        target=aux['belief'].reshape(-1);belief+=np.bincount(target[target>=0],minlength=90)
    for op,belief in counts.values():
        op/=op.sum();belief/=belief.sum()
    summaries={}
    for mode in ('full-history','zero-history'):
        totals={native:np.zeros(9,dtype=np.float64) for native in (True,False)}
        blocks={native:{} for native in (True,False)}
        with torch.inference_mode():
            for index,entry in enumerate(data['dev']):
                base=Path(entry.get('aux_base',local/f'dev-{index:02d}'))
                rows=np.memmap(entry['source'],mode='r',dtype=DTYPE)
                x=np.memmap(entry['inputs'],mode='r',dtype='<f4',shape=(len(rows),525))
                h=np.memmap(local/'history-v2'/f'dev-{index:03d}.history.bin',mode='r',dtype='<f4',shape=(len(rows),16,32))
                pool=np.memmap(str(base)+'.pool.bin',mode='r',dtype='<f4',shape=(len(rows),90))
                aux=np.memmap(str(base)+'.aux.bin',mode='r',dtype=AUX,shape=(len(rows),))
                native=entry['native'];op_frequency,belief_frequency=counts[native]
                for start in range(0,len(rows),args.batch):
                    stop=min(len(rows),start+args.batch)
                    xx=torch.from_numpy(np.array(x[start:stop],copy=True))
                    hh=torch.from_numpy(np.array(h[start:stop],copy=True))
                    pp=torch.from_numpy(np.array(pool[start:stop],copy=True))
                    if mode=='zero-history':hh.zero_()
                    # No auxiliary/privileged tensor is passed to the model.
                    _,_,opponent,belief=model(xx,hh,pp)
                    op_log=opponent.log_softmax(-1).numpy()
                    belief_log=belief.log_softmax(-1).numpy()
                    assert np.isfinite(op_log).all() and np.isfinite(belief_log).all()
                    for j in range(stop-start):
                        block=blocks[native].setdefault(int(rows[start+j]['setup']),np.zeros(5))
                        target=int(aux[start+j]['opponent'])
                        if target>=0:
                            loss=-float(op_log[j,target]);freq=-float(np.log(op_frequency[target]))
                            totals[native][:3]+=[loss,int(op_log[j].argmax()==target),1]
                            block[:2]+=[loss-freq,1]
                        for slot,target in enumerate(aux[start+j]['belief']):
                            if target<0:continue
                            tier=int(np.rint(x[start+j,515+slot]*3))
                            allowed=(pool[start+j]>0)&(tiers==tier)
                            assert allowed[target] and belief_log[j,slot,target]>-1e8
                            uniform=float(np.log(allowed.sum()))
                            frequency=-float(np.log(belief_frequency[target]/belief_frequency[allowed].sum()))
                            loss=-float(belief_log[j,slot,target])
                            totals[native][3:]+=[loss,int(belief_log[j,slot].argmax()==target),1,uniform,frequency,0]
                            block[2:]+=[loss-uniform,1,loss-frequency]
                print(json.dumps(dict(mode=mode,dev_shard=index,seconds=time.monotonic()-started)),flush=True)
        results={}
        for native,total in totals.items():
            key='native' if native else 'canonical'
            result=dict(opponent_ce=total[0]/total[2],opponent_accuracy=total[1]/total[2],opponent_targets=int(total[2]),
                hidden_ce=total[3]/total[5],hidden_accuracy=total[4]/total[5],hidden_targets=int(total[5]),
                hidden_uniform_ce=total[6]/total[5],hidden_frequency_ce=total[7]/total[5],
                independent_setups=len(blocks[native]),setup_bootstrap=bootstrap(blocks[native],args.bootstrap_repeats,800000049))
            for name in ('opponent_targets','hidden_targets'):assert result[name]==baseline['results'][key][name]
            if mode=='full-history':
                manifest=json.loads(args.checkpoint.with_name('manifest.json').read_text())
                assert sha(args.checkpoint)==manifest['checkpoint_sha256']
                selected=manifest['initial'] if payload['epoch']==0 else manifest['history'][payload['epoch']-1]
                for name in ('opponent_ce','hidden_ce','opponent_accuracy','hidden_accuracy'):
                    assert abs(result[name]-selected[key][name])<2e-5,(key,name,result[name],selected[key][name])
            results[key]=result
        summaries[mode]=results
    args.output.write_text(json.dumps(dict(checkpoint=str(args.checkpoint),checkpoint_sha256=sha(args.checkpoint),
        selected_epoch=payload['epoch'],registry_sha256=sha(registry),script_sha256=sha(Path(__file__)),
        device='cpu',torch_threads=2,bootstrap_repeats=args.bootstrap_repeats,bootstrap_seed=800000049,
        scope='Exploratory diagnostics on the fixed dev split; no weight or search-budget selection; bootstrap whole independent setups',
        label_boundary='Model receives public state, preceding public events and public pool only; privileged targets enter scoring after inference',
        seconds=time.monotonic()-started,results=summaries),indent=2)+'\n')
    print(json.dumps(summaries),flush=True)


if __name__=='__main__':main()
