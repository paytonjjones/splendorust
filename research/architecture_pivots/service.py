"""Opt-in batch inference: fixed public tensors in, policy/value tensors out."""
import argparse
import hashlib
import json
import queue
import socket
import threading
import time

import numpy as np
import torch
from models import load, forward

INPUTS = 525 + 16*32 + 90


def receive(conn, length):
    chunks = bytearray()
    while len(chunks) < length:
        chunk = conn.recv(length-len(chunks))
        if not chunk:
            raise EOFError
        chunks.extend(chunk)
    return chunks


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--model',action='append',required=True,help='slot:checkpoint path')
    ap.add_argument('--port',type=int,default=19531)
    ap.add_argument('--device',default='mps')
    ap.add_argument('--batch',type=int,default=256)
    ap.add_argument('--delay-ms',type=float,default=1)
    ap.add_argument('--fast-entities',action='store_true')
    args=ap.parse_args();torch.set_num_threads(4)
    models={};hashes={};pending={}
    for entry in args.model:
        slot,path=entry.split(':',1);slot=int(slot)
        models[slot]=load(path,args.device)
        if hasattr(models[slot][0],'fast_tokenization'):
            models[slot][0].fast_tokenization=args.fast_entities
        hashes[slot]=hashlib.sha256(open(path,'rb').read()).digest()
        pending[slot]=queue.Queue()
    def client(conn):
        try:
            slot=int.from_bytes(receive(conn,4),'little')
            conn.sendall(hashes[slot])
            while True:
                tensor=np.frombuffer(receive(conn,INPUTS*4),dtype='<f4').copy()
                assert np.isfinite(tensor).all()
                reply=queue.Queue(maxsize=1)
                pending[slot].put((tensor,reply))
                result=reply.get()
                conn.sendall(result)
        except (EOFError,ConnectionError):
            pass
        finally:
            conn.close()
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',args.port));listener.listen(256)
    def accept():
        while True:
            conn,_=listener.accept();conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            threading.Thread(target=client,args=(conn,),daemon=True).start()
    threading.Thread(target=accept,daemon=True).start()
    print(json.dumps(dict(ready=True,port=args.port,device=args.device,batch=args.batch,
        delay_ms=args.delay_ms,fast_entities=args.fast_entities,models={s:dict(kind=p['kind'],sha256=hashes[s].hex()) for s,(_,p) in models.items()})),flush=True)
    calls=0;batches=0;start=time.monotonic();last=start
    with torch.inference_mode():
        while True:
            idle=True
            for slot,q in pending.items():
                try:
                    requests=[q.get_nowait()]
                except queue.Empty:
                    continue
                idle=False;deadline=time.monotonic()+args.delay_ms/1000
                while len(requests)<args.batch:
                    try:
                        requests.append(q.get(timeout=max(0,deadline-time.monotonic())))
                    except queue.Empty:
                        break
                # Fixed shape also makes arithmetic independent of queue occupancy.
                arrays=np.zeros((args.batch,INPUTS),dtype='<f4')
                arrays[:len(requests)]=np.stack([a for a,_ in requests])
                x=torch.from_numpy(arrays[:,:525]).to(args.device)
                h=torch.from_numpy(arrays[:,525:1037].reshape(-1,16,32)).to(args.device)
                pool=torch.from_numpy(arrays[:,1037:]).to(args.device)
                model,payload=models[slot]
                if payload.get('history_ablation')=='no-history':h.zero_()
                result=forward(model,payload['kind'],x,h,pool)
                outputs=torch.cat(result[:2],dim=-1).cpu().numpy().astype('<f4')
                assert np.isfinite(outputs).all()
                for output,(_,reply) in zip(outputs[:len(requests)],requests):
                    reply.put(output.tobytes())
                calls+=len(requests);batches+=1
            if idle:
                time.sleep(.0001)
            if time.monotonic()-last>30:
                print(json.dumps(dict(calls=calls,batches=batches,seconds=time.monotonic()-start,
                    mean_batch=calls/max(1,batches))),flush=True);last=time.monotonic()


if __name__=='__main__':
    main()
