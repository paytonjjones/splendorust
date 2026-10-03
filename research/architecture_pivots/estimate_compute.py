"""Estimate dense forward MACs from frozen weights; not a runtime benchmark."""
import hashlib
import json
from pathlib import Path
import torch

HERE=Path(__file__).resolve().parent


def main():
    result={}
    for kind in ('capacity','entity','history'):
        path=HERE/f'expanded-{kind}/model.pt'
        payload=torch.load(path,map_location='cpu',weights_only=True)
        state=payload['state_dict']
        if kind=='capacity':
            components=dict(dense_linear=sum(t.numel() for k,t in state.items()
                if k.endswith('.weight') and t.ndim==2))
            tokens=1
        else:
            tokens=state['identity'].shape[0]
            history_tokens=state['history_position'].shape[0] if kind=='history' else 0
            width=state['project.weight'].shape[0]
            total_tokens=tokens+history_tokens
            layers=[k.removesuffix('.self_attn.in_proj_weight') for k in state
                    if k.endswith('.self_attn.in_proj_weight')]
            projection=total_tokens*sum(state[k+'.self_attn.in_proj_weight'].numel()
                +state[k+'.self_attn.out_proj.weight'].numel() for k in layers)
            feedforward=total_tokens*sum(state[k+'.linear1.weight'].numel()
                +state[k+'.linear2.weight'].numel() for k in layers)
            components=dict(token_projection=tokens*state['project.weight'].numel(),
                attention_projections=projection,attention_scores_and_values=2*len(layers)*total_tokens**2*width,
                feedforward=feedforward,policy_value=state['policy.weight'].numel()+state['value.weight'].numel())
            if history_tokens:
                components.update(history_projection=history_tokens*state['history_project.weight'].numel(),
                    auxiliary_and_feedback=sum(state[k+'.weight'].numel() for k in ('opponent','belief','feedback')))
            tokens=total_tokens
        macs=sum(components.values())
        result[kind]=dict(checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            tokens=tokens,components_macs=components,forward_macs_per_position=macs,
            estimated_flops_per_position=2*macs)
    residual=result['capacity']['forward_macs_per_position']
    for row in result.values():row['mac_ratio_to_residual']=row['forward_macs_per_position']/residual
    output=dict(models=result,scope='Dense linear and attention multiply-accumulates only; one MAC counted as two FLOPs. Excludes activation, normalization, masks, token encoding, transport, queueing, search and backward pass. Includes all padded tokens. Runtime is measured separately.',
        fixed_batch32='Each service forward evaluates 32 padded positions even at lower occupancy.')
    (HERE/'estimated-compute.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
