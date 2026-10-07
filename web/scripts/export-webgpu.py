#!/usr/bin/env python3
"""Export the frozen SPENTY01 weights. No training or parameter changes."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import helper as h, numpy_helper as nh, TensorProto as T

parser = argparse.ArgumentParser()
parser.add_argument('--batch-size', type=int, choices=[1,2,4,8], default=1)
batch = parser.parse_args().batch_size
ROOT = Path(__file__).resolve().parents[2]
champion = json.loads((ROOT / 'research/STRENGTH_CHAMPION.json').read_text())
source = ROOT / champion['model']
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == champion['model_sha256']
assert raw[:8] == b'SPENTY01'
weights = np.frombuffer(raw[8:], dtype='<f4')
offset = 0
nodes, initializers = [], []

def constant(name, values, dtype=np.float32):
    initializers.append(nh.from_array(np.asarray(values, dtype=dtype), name))
    return name

def take(name, shape):
    global offset
    count = int(np.prod(shape))
    a = weights[offset:offset+count].copy().reshape(shape)
    offset += count
    return constant(name, a)

def node(op, inputs, output, **attrs):
    nodes.append(h.make_node(op, inputs, [output], **attrs))
    return output

def linear(prefix, x, width, out):
    w = take(prefix + '.weight', (out, width))
    b = take(prefix + '.bias', (out,))
    wt = node('Transpose', [w], prefix + '.wt', perm=[1,0])
    product = node('MatMul', [x, wt], prefix + '.matmul')
    return node('Add', [product,b], prefix + '.out')

def norm(prefix, x):
    scale = take(prefix + '.scale', (256,))
    bias = take(prefix + '.bias', (256,))
    return node('LayerNormalization', [x,scale,bias], prefix + '.out', axis=-1, epsilon=1e-5)

identity = take('identity', (1,31,256))
z = linear('project', 'tokens', 48, 256)
z = node('Add', [z, identity], 'embedding')
constant('headsShape', [batch,31,8,32], np.int64)
constant('mergedShape', [batch,31,256], np.int64)
constant('attentionScale', np.sqrt(32))
constant('sqrt2', np.sqrt(2))
constant('one', 1)
constant('half', 0.5)
constant('zeroIndex', 0, np.int64)
for layer in range(6):
    p = f'layer{layer}'
    # The native file stores all four linears before both layer norms.
    params = {}
    for name, width, out in [('qkv',256,768),('proj',256,256),('ff1',256,1024),('ff2',1024,256)]:
        params[name] = (take(f'{p}.{name}.weight',(out,width)), take(f'{p}.{name}.bias',(out,)))
    n = norm(p+'.norm1', z)
    n2scale = take(p+'.norm2.scale',(256,)); n2bias = take(p+'.norm2.bias',(256,))
    def dense(name, x):
        w,b = params[name]
        wt=node('Transpose',[w],p+'.'+name+'.wt',perm=[1,0])
        mm=node('MatMul',[x,wt],p+'.'+name+'.matmul')
        return node('Add',[mm,b],p+'.'+name+'.out')
    qkv = dense('qkv',n)
    outputs=[p+'.q',p+'.k',p+'.v']
    constant(p+'.splits',[256,256,256],np.int64)
    nodes.append(h.make_node('Split',[qkv,p+'.splits'],outputs,axis=-1))
    reshaped=[]
    for label in ['q','k','v']:
        r=node('Reshape',[p+'.'+label,'headsShape'],p+'.'+label+'.reshape')
        reshaped.append(node('Transpose',[r],p+'.'+label+'.heads',perm=[0,2,1,3]))
    q,k,v=reshaped
    kt=node('Transpose',[k],p+'.kt',perm=[0,1,3,2])
    score=node('MatMul',[q,kt],p+'.scores')
    score=node('Div',[score,'attentionScale'],p+'.scaled')
    prob=node('Softmax',[score],p+'.prob',axis=-1)
    a=node('MatMul',[prob,v],p+'.attention')
    a=node('Transpose',[a],p+'.attnTranspose',perm=[0,2,1,3])
    a=node('Reshape',[a,'mergedShape'],p+'.merged')
    proj=dense('proj',a)
    z=node('Add',[z,proj],p+'.residual1')
    n=node('LayerNormalization',[z,n2scale,n2bias],p+'.norm2.out',axis=-1,epsilon=1e-5)
    u=dense('ff1',n)
    e=node('Div',[u,'sqrt2'],p+'.gelu.div')
    e=node('Erf',[e],p+'.gelu.erf')
    e=node('Add',[e,'one'],p+'.gelu.plus')
    e=node('Mul',[u,e],p+'.gelu.mul')
    e=node('Mul',[e,'half'],p+'.gelu.out')
    d=dense('ff2',e)
    z=node('Add',[z,d],p+'.residual2')
cls=node('Gather',[z,'zeroIndex'],'cls',axis=1)
cls=norm('finalNorm',cls)
pi=linear('policy',cls,256,81)
v=linear('value',cls,256,2)
node('Identity',[pi],'logits')
node('Tanh',[v],'values')
assert offset == weights.size, (offset,weights.size)
graph=h.make_graph(nodes,'frozen-entity-champion',[h.make_tensor_value_info('tokens',T.FLOAT,[batch,31,48])],[h.make_tensor_value_info('logits',T.FLOAT,[batch,81]),h.make_tensor_value_info('values',T.FLOAT,[batch,2])],initializers)
model=h.make_model(graph,opset_imports=[h.make_opsetid('',17)],producer_name='splendorust-frozen-export',ir_version=9)
onnx.checker.check_model(model)
body=model.SerializeToString(); digest=hashlib.sha256(body).hexdigest()
dest=ROOT/'web/public/models'/f'{digest}.onnx';dest.write_bytes(body)
manifest={'schema':'splendor-webgpu-model-v1','sourceSha256':champion['model_sha256'],'sha256':digest,'bytes':len(body),'url':f'/models/{digest}.onnx','input':'tokens','shape':[batch,31,48],'precision':'float32'}
(ROOT/'web/public'/('webgpu.json' if batch == 1 else f'webgpu-batch{batch}.json')).write_text(json.dumps(manifest,indent=2)+'\n')
(ROOT/'research/webgpu-20261006'/('export.json' if batch == 1 else f'batch-export{batch}.json')).write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
