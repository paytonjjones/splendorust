"""Check parent preservation and learned-history paths before a possible pivot."""
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from capacity_history import CapacityHistory
from models import ROOT, load

def main():
    torch.manual_seed(800000031)
    torch.set_num_threads(1)
    local=ROOT/'local/research/architecture-pivots'
    x=np.memmap(local/'dev-00.inputs.bin',mode='r',dtype='<f4').reshape(-1,525)
    h=np.memmap(local/'history-v2/dev-000.history.bin',mode='r',dtype='<f4').reshape(-1,16,32)
    p=np.memmap(local/'dev-00.pool.bin',mode='r',dtype='<f4').reshape(-1,90)
    # Include actual past events and hidden reservations, with no labels in inputs.
    candidates=np.flatnonzero((x[:,512:515].sum(-1)>0)&(h[:,:,0].sum(-1)>0))
    assert len(candidates)>=32
    ix=candidates[np.linspace(0,len(candidates)-1,32,dtype=int)]
    arrays=[np.array(v[ix],copy=True) for v in (x,h,p)]
    parent,_=load(ROOT/'research/architecture_pivots/capacity/model.pt')
    model=CapacityHistory().eval()
    missing,unexpected=model.load_state_dict(parent.state_dict(),strict=False)
    assert not unexpected and all(k.startswith(('history_','opponent.','belief.','feedback.')) or k=='tiers' for k in missing)
    results=[]
    for device in ['cpu']+(['mps'] if torch.backends.mps.is_available() else []):
        parent.to(device);model.to(device)
        xx,hh,pool=[torch.from_numpy(a).to(device) for a in arrays]
        with torch.inference_mode():
            a=parent(xx);b=model(xx,hh,pool)
            assert all(torch.equal(u,v) for u,v in zip(a,b[:2])),'extension changes its parent before training'
            active=xx[:,512:515]>0
            allowed=(pool[:,None,:]>0)&(torch.round(xx[:,515:518]*3).long()[:,:,None]==model.tiers[None,None,:])
            forbidden=active[:,:,None]&~allowed
            assert (b[3][forbidden]==-1e9).all()
        results.append(dict(device=device,initial_parent_predictions_bit_exact=True,public_belief_support_valid=True))
    model.cpu().train();xx,hh,pool=[torch.from_numpy(a) for a in arrays]
    optimizer=torch.optim.SGD(model.parameters(),lr=.01)
    for _ in range(2):
        prediction=model(xx,hh,pool)
        target=prediction[3].detach().argmax(-1)
        loss=prediction[0].square().mean()+prediction[1].square().mean()+torch.nn.functional.cross_entropy(prediction[2],torch.zeros(32,dtype=torch.long))+torch.nn.functional.cross_entropy(prediction[3].flatten(0,1),target.flatten())
        optimizer.zero_grad();loss.backward();optimizer.step()
    gradient=model.history_blocks.layers[0].self_attn.in_proj_weight.grad
    assert gradient is not None and torch.isfinite(gradient).all() and gradient.abs().sum()>0
    path=ROOT/'research/architecture_pivots/capacity-history-infrastructure.json'
    path.write_text(json.dumps(dict(parameters=sum(v.numel() for v in model.parameters()),rows=32,
        results=results,history_attention_receives_gradient=True,
        scope='Infrastructure only; no trained fit or strength result',
        source_sha256=hashlib.sha256(Path(__file__).with_name('capacity_history.py').read_bytes()).hexdigest()),indent=2)+'\n')
    print(path.read_text())

if __name__=='__main__':main()
