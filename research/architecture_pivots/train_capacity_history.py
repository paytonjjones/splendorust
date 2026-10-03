"""Version-two history training on the same state, policy and value rows."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'research'))
sys.path.insert(0, str(ROOT/'research/e95'))
from flywheel_model import open_rows, check_rows, sha
from public_model import inputs
from capacity_history import create, forward, load


def prepare(scale='initial'):
    directory = ROOT/'local/research/architecture-pivots'
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory/('data.json' if scale=='initial' else 'expanded-data.json')
    if receipt.exists():
        result = json.loads(receipt.read_text())
        for split in ('train', 'dev'):
            for entry in result[split]:
                for field in ('source', 'context', 'inputs'):
                    assert sha(entry[field]) == entry[field+'_sha256']
        return result
    if scale=='expanded':
        return prepare_expanded(directory,receipt)
    native = ROOT/'local/research/e95'
    result = {}
    sets = {}
    for split in ('train', 'dev'):
        paths = sorted((native/split).glob('*/data.bin'))
        paths += [ROOT/('local/research/e87/train/004000.bin' if split == 'train'
                       else 'local/research/e87/dev.bin')]
        groups, ids, _ = open_rows(paths)
        sets[split] = ids
        entries = []
        for index, (path, rows) in enumerate(zip(paths, groups)):
            check_rows(rows)
            assert np.isfinite(rows['outcome']).all()
            context_path = path.with_suffix('.context.bin')
            context = np.fromfile(context_path, dtype='<f4').reshape(-1,7)
            assert len(context) == len(rows)
            dest = directory/f'{split}-{index:02d}.inputs.bin'
            packed = np.memmap(dest, mode='w+', dtype='<f4', shape=(len(rows),525))
            is_native = path.is_relative_to(native)
            for i in range(0, len(rows), 4096):
                packed[i:i+4096] = inputs(rows['x'][i:i+4096], context[i:i+4096], is_native)
            packed.flush()
            assert np.isfinite(packed).all()
            entries.append(dict(source=str(path),context=str(context_path),inputs=str(dest),
                source_sha256=sha(path), context_sha256=sha(context_path),inputs_sha256=sha(dest),
                native=is_native,rows=len(rows)))
        result[split] = entries
    assert not sets['train'] & sets['dev']
    result['setup_counts'] = {k: len(v) for k,v in sets.items()}
    receipt.write_text(json.dumps(result, indent=2)+'\n')
    return result


def prepare_expanded(directory,receipt):
    initial=prepare()
    from copy import deepcopy
    result=deepcopy(initial)
    expansion=ROOT/'local/research/architecture-pivots/expansion/train'
    assert (ROOT/'research/architecture_pivots/expansion/complete.json').exists()
    native_paths=sorted(expansion.glob('*/data.bin'))
    assert len(native_paths)==100
    canonical_paths=sorted((directory/'expansion/canonical').glob('*.bin'))
    canonical_paths=[p for p in canonical_paths if p.name.endswith('.data.bin')]
    assert len(canonical_paths)==4
    for native,paths,label in [(True,native_paths,'expanded-native'),(False,canonical_paths,'expanded-canonical')]:
        for index,path in enumerate(paths):
            rows,_,_=open_rows([path]);rows=rows[0];check_rows(rows)
            assert np.isfinite(rows['outcome']).all()
            context_path=path.with_suffix('.context.bin')
            context=np.fromfile(context_path,dtype='<f4').reshape(-1,7)
            dest=directory/f'{label}-{index:02d}.inputs.bin'
            packed=np.memmap(dest,mode='w+',dtype='<f4',shape=(len(rows),525))
            for i in range(0,len(rows),4096):packed[i:i+4096]=inputs(rows['x'][i:i+4096],context[i:i+4096],native)
            packed.flush();assert np.isfinite(packed).all()
            result['train'].append(dict(source=str(path),context=str(context_path),inputs=str(dest),
                source_sha256=sha(path),context_sha256=sha(context_path),inputs_sha256=sha(dest),
                native=native,rows=len(rows),aux_base=str(directory/f'{label}-{index:02d}')))
    _,train_ids,_=open_rows([e['source'] for e in result['train']])
    _,dev_ids,_=open_rows([e['source'] for e in result['dev']])
    assert not train_ids&dev_ids
    result['setup_counts']=dict(train=len(train_ids),dev=len(dev_ids))
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    return result


def train(args):
    from flywheel_model import DTYPE
    assert args.kind in ('history','capacity') and args.data_scale=='expanded'
    history_version=2 if args.kind=='history' else 0
    start = time.monotonic()
    data = prepare(args.data_scale)
    args.output.mkdir(parents=True, exist_ok=False)
    seed = 800000031
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True, warn_only=True)
    rng = np.random.default_rng(seed)
    model = create(args.kind).to(args.device)
    if hasattr(model,'fast_tokenization'):model.fast_tokenization=args.fast_entities
    if args.parent:
        parent,payload=load(args.parent)
        assert payload['kind']=='capacity' and args.kind in ('capacity','history')
        missing,unexpected=model.load_state_dict(parent.state_dict(),strict=False)
        assert not unexpected
        assert all(key.startswith(('history_','opponent.','belief.','feedback.')) or key=='tiers' for key in missing)
    lr = 1e-4 if args.kind == 'small' or args.parent else 3e-4
    opt = torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(opt,args.epochs,eta_min=lr/10)
    groups = {}
    extras = {}
    for split in ('train','dev'):
        groups[split] = [(np.memmap(e['source'],mode='r',dtype=DTYPE),
                        np.memmap(e['inputs'],mode='r',dtype='<f4',shape=(e['rows'],525)),
                        e['native']) for e in data[split]]
        if args.kind=='history':
            from history_data import AUX
            extras[split]=[]
            for index,e in enumerate(data[split]):
                base=Path(e.get('aux_base',ROOT/'local/research/architecture-pivots'/f'{split}-{index:02d}'))
                extras[split].append((
                    np.memmap(ROOT/'local/research/architecture-pivots/history-v2'/f'{split}-{index:03d}.history.bin',mode='r',dtype='<f4',shape=(e['rows'],16,32)),
                    np.memmap(str(base)+'.aux.bin',mode='r',dtype=AUX,shape=(e['rows'],)),
                    np.memmap(str(base)+'.pool.bin',mode='r',dtype='<f4',shape=(e['rows'],90))))

    def tensors(r,x):
        return [torch.from_numpy(np.array(v,copy=True)).to(args.device)
                for v in (x,r['mask'],r['policy'],r['teacher'],r['outcome'])]

    def loss_values(result,mask,policy,teacher,outcome,aux=None):
        logits,v = result[:2]
        logp = logits.masked_fill(mask == 0,-1e9).log_softmax(-1)
        target = torch.where(torch.isfinite(teacher),(teacher+outcome)/2,outcome)*2-1
        loss = -(policy*logp).sum(-1).mean() + ((v[:,0]-target)**2+(v[:,1]+target)**2).mean()/2
        if aux is not None:
            opponent,belief=aux
            valid=opponent>=0
            if valid.any():loss=loss+.25*torch.nn.functional.cross_entropy(result[2][valid],opponent[valid])
            valid=belief>=0
            if valid.any():
                predictions=result[3][valid];targets=belief[valid]
                assert (predictions.gather(1,targets[:,None])>-1e8).all(),'hidden target outside public pool/tier'
                loss=loss+.10*torch.nn.functional.cross_entropy(predictions,targets)
        return loss,logp,v

    def history_tensors(split,index,ix):
        if args.kind!='history':return None,None,None
        h,a,pool=extras[split][index]
        values=[np.array(v,copy=True) for v in (h[ix],pool[ix],a['opponent'][ix],a['belief'][ix])]
        history,pool,opponent,belief=[torch.from_numpy(v).to(args.device) for v in values]
        if args.history_ablation=='no-history':history.zero_()
        return history,pool,(opponent.long(),belief.long())

    def evaluate():
        model.eval()
        sums = {k:np.zeros(5) for k in ('native','canonical')}
        aux_sums={k:np.zeros(7) for k in sums}
        with torch.no_grad():
            for index,(rows,x,native) in enumerate(groups['dev']):
                total = sums['native' if native else 'canonical']
                for i in range(0,len(rows),args.batch):
                    xx,mask,policy,teacher,outcome=tensors(rows[i:i+args.batch],x[i:i+args.batch])
                    h,pool,aux=history_tensors('dev',index,slice(i,i+args.batch))
                    result=forward(model,args.kind,xx,h,pool)
                    _,logp,v=loss_values(result,mask,policy,teacher,outcome)
                    if aux is not None:
                        a=aux_sums['native' if native else 'canonical']
                        opponent,belief=aux
                        valid=opponent>=0
                        if valid.any():
                            logits=result[2][valid];targets=opponent[valid]
                            a[:3]+=np.array([torch.nn.functional.cross_entropy(logits,targets,reduction='sum').item(),(logits.argmax(-1)==targets).sum().item(),len(targets)])
                        valid=belief>=0
                        if valid.any():
                            logits=result[3][valid];targets=belief[valid]
                            support=(logits>-1e8).sum(-1)
                            a[3:]+=np.array([torch.nn.functional.cross_entropy(logits,targets,reduction='sum').item(),(logits.argmax(-1)==targets).sum().item(),support.float().log().sum().item(),len(targets)])
                    prob=(v[:,0]+1)/2
                    target=torch.where(torch.isfinite(teacher),(teacher+outcome)/2,outcome)
                    total+=np.array([-(policy*logp).sum().item(),
                        (logp.argmax(-1)==policy.argmax(-1)).sum().item(),
                        ((prob-outcome)**2).sum().item(),((prob-target)**2).sum().item(),len(xx)])
        metrics={k:dict(policy_ce=v[0]/v[4],policy_accuracy=v[1]/v[4],
                outcome_brier=v[2]/v[4],target_brier=v[3]/v[4],rows=int(v[4])) for k,v in sums.items()}
        for k,a in aux_sums.items():
            if a[2]:metrics[k].update(opponent_ce=a[0]/a[2],opponent_accuracy=a[1]/a[2],opponent_targets=int(a[2]))
            if a[6]:metrics[k].update(hidden_ce=a[3]/a[6],hidden_accuracy=a[4]/a[6],hidden_uniform_ce=a[5]/a[6],hidden_targets=int(a[6]))
        total=sum(sums.values())
        metrics['selection_score']=(total[0]+4*total[2])/total[4]
        return metrics

    def save(name,epoch):
        torch.save(dict(kind=args.kind,epoch=epoch,seed=seed,backbone='capacity',
            history_ablation=args.history_ablation,history_version=history_version,
            fast_entities=args.fast_entities,
            state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()}),args.output/name)

    extra_hashes={}
    for split in ('train','dev'):
        extra_hashes[split]=[]
        for index,e in enumerate(data[split]):
            base=Path(e.get('aux_base',ROOT/'local/research/architecture-pivots'/f'{split}-{index:02d}'))
            paths=[ROOT/'local/research/architecture-pivots/history-v2'/f'{split}-{index:03d}.history.bin',Path(str(base)+'.aux.bin'),Path(str(base)+'.pool.bin')]
            extra_hashes[split].append({str(p):sha(p) for p in paths})
    parameters=sum(p.numel() for p in model.parameters())
    initial=evaluate()
    print(json.dumps(dict(stage='initial',parameters=parameters,**initial)),flush=True)
    best=initial['selection_score'];best_epoch=0
    save('model.pt',0)
    metrics=[]
    for epoch in range(1,args.epochs+1):
        model.train();trained=0;train_loss=0.;epoch_start=time.monotonic()
        for j in rng.permutation(len(groups['train'])):
            rows,x,_=groups['train'][j];order=rng.permutation(len(rows))
            for i in range(0,len(rows),args.batch):
                ix=order[i:i+args.batch]
                xx,mask,policy,teacher,outcome=tensors(rows[ix],x[ix])
                h,pool,aux=history_tensors('train',j,ix)
                if args.history_ablation=='history-only':aux=None
                loss,_,_=loss_values(forward(model,args.kind,xx,h,pool),mask,policy,teacher,outcome,aux)
                assert torch.isfinite(loss),'non-finite loss'
                opt.zero_grad(set_to_none=True);loss.backward()
                norm=torch.nn.utils.clip_grad_norm_(model.parameters(),5)
                assert torch.isfinite(norm),'non-finite gradient'
                opt.step();trained+=len(ix);train_loss+=loss.item()*len(ix)
        schedule.step()
        m=evaluate();m.update(epoch=epoch,trained_rows=trained,train_loss=train_loss/trained,
            epoch_seconds=time.monotonic()-epoch_start,seconds=time.monotonic()-start)
        metrics.append(m);print(json.dumps(m),flush=True)
        if m['selection_score']<best:
            best=m['selection_score'];best_epoch=epoch;save('model.pt',epoch)
        save('latest.pt',epoch)
        manifest=dict(kind=args.kind,backbone='capacity',parameters=parameters,seed=seed,epochs=args.epochs,
            batch=args.batch,learning_rate=lr,device=args.device,initial=initial,history=metrics,
            best_epoch=best_epoch,seconds=time.monotonic()-start,data=data,
            scripts={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('models.py'),Path(__file__).with_name('capacity_history.py')]},
            checkpoint_sha256=sha(args.output/'model.pt'),
            parent_sha256=sha(args.parent) if args.parent else None,history_ablation=args.history_ablation,
            history_version=history_version,
            data_scale=args.data_scale,extra_inputs_sha256=extra_hashes,
            fast_entities=args.fast_entities,
            selection='dev policy CE +4 outcome Brier',
            determinism='Fixed RNG and data order; MPS bitwise repeatability is not guaranteed')
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--kind',choices=('capacity','history'),required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--epochs',type=int,default=12)
    ap.add_argument('--batch',type=int,default=512)
    ap.add_argument('--device',default='mps')
    ap.add_argument('--parent',type=Path)
    ap.add_argument('--history-ablation',choices=('full','history-only','no-history'),default='full')
    ap.add_argument('--data-scale',choices=('initial','expanded'),default='initial')
    ap.add_argument('--fast-entities',action='store_true')
    train(ap.parse_args())
