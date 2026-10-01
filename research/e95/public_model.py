"""Fast E81 trunk with deterministic public inputs and public rules identity."""
import copy,struct,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'));sys.path.insert(0,str(ROOT/'research/e86'))
from flywheel_model import bootstrap,raw,export as old_export
from public_features import batch

def load(warmstart):
 payload=torch.load(warmstart,map_location='cpu',weights_only=True)
 if payload.get('input_rows')==75:
  model=bootstrap(ROOT/'research/e81/model/model.pt')
 else:model=bootstrap(warmstart)
 old=model.first_layer.linear;layer=copy.deepcopy(old);layer.in_features=75
 layer.weight=torch.nn.Parameter(old.weight.new_zeros((56,75)))
 with torch.no_grad():layer.weight[:,:56].copy_(old.weight)
 model.first_layer.linear=layer;model.input_rows=75
 if payload.get('input_rows')==75:model.load_state_dict(payload['state_dict'],strict=True)
 return model

def pack(mean,public,native):
 mean=np.asarray(mean,dtype='<f4');public=np.asarray(public,dtype='<f4');assert mean.shape[-1]==392 and public.shape[-1]==519
 result=np.zeros((len(mean),525),dtype='<f4');result[:,:392]=mean;result[:,392:519]=public[:,392:];result[:,519]=native
 return result

def inputs(x,context,native):
 mean,public=batch(x,context);return pack(mean,public,native)

def export(model,path):
 # Existing exporter serializes the same trunk/head parameters and checks length.
 old_export(model,path)
 payload=Path(path).read_bytes();depth=len(model.trunk)
 if depth>1:assert payload[:8]==b'SPMOBIL1';payload=payload[12:]
 Path(path).write_bytes(b'SPPUB751'+struct.pack('<I',depth)+payload)
