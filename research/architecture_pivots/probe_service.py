"""Check numerical identity by queue occupancy and measure tensor-service cost."""
import argparse
import concurrent.futures
import hashlib
import json
import socket
import sys
import time
from pathlib import Path
import numpy as np
from models import ROOT
from service import INPUTS,receive


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',type=Path,required=True)
    ap.add_argument('--slot',type=int,required=True);ap.add_argument('--port',type=int,default=19531)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--calls',type=int,default=256)
    args=ap.parse_args();expected=hashlib.sha256(args.checkpoint.read_bytes()).digest()
    source=ROOT/'local/research/architecture-pivots/dev-00.inputs.bin'
    x=np.memmap(source,mode='r',dtype='<f4').reshape(-1,525)
    pool=np.memmap(source.with_name('dev-00.pool.bin'),mode='r',dtype='<f4').reshape(-1,90)
    fixture=np.zeros((16,INPUTS),dtype='<f4');fixture[:,:525]=x[:16];fixture[:,1037:]=pool[:16]
    manifest=json.loads(args.checkpoint.with_name('manifest.json').read_text())
    history_version=manifest.get('history_version',1)
    history_path=(source.parent/'history-v2/dev-000.history.bin' if history_version==2
        else source.with_name('dev-00.history.bin'))
    history=np.memmap(history_path,mode='r',dtype='<f4').reshape(-1,16,32)
    fixture[:,525:1037]=history[:16].reshape(16,-1)
    def requests(count,offset=0):
        conn=socket.create_connection(('127.0.0.1',args.port));conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        conn.sendall(args.slot.to_bytes(4,'little'));assert bytes(receive(conn,32))==expected
        values=[]
        try:
            for i in range(count):
                index=(offset+i)%len(fixture);conn.sendall(fixture[index].tobytes())
                values.append((index,np.frombuffer(receive(conn,83*4),dtype='<f4').copy()))
        finally:conn.close()
        return values
    reference=dict(requests(16));results=[];bit_exact=True;maximum=0.
    for workers in (1,4,8,14,32):
        start=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            jobs=[executor.submit(requests,args.calls//workers+(i<args.calls%workers),i) for i in range(workers)]
            for future in jobs:
                for index,value in future.result():
                    bit_exact=bit_exact and np.array_equal(value.view(np.uint32),reference[index].view(np.uint32))
                    maximum=max(maximum,float(np.max(np.abs(value-reference[index]))))
        elapsed=time.monotonic()-start
        results.append(dict(workers=workers,calls=args.calls,seconds=elapsed,calls_per_second=args.calls/elapsed))
    args.output.write_text(json.dumps(dict(checkpoint_sha256=expected.hex(),history_version=history_version,
        history_fixture=str(history_path),history_fixture_sha256=hashlib.sha256(history_path.read_bytes()).hexdigest(),
        shape_occupancy_bit_exact=bit_exact,
        maximum_abs_error=maximum,shared_host=True,scope='Tensor service only, including client queue/socket overhead',
        results=results),indent=2)+'\n')
    assert bit_exact,'occupancy-dependent arithmetic; investigate before fixed-budget arena'


if __name__=='__main__':main()
