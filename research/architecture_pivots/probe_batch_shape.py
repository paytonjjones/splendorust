"""Compare immutable model outputs between fixed inference batch shapes."""
import concurrent.futures
import hashlib
import json
import socket
from pathlib import Path
import numpy as np
from models import ROOT
from service import receive,INPUTS

def main():
    here=Path(__file__).parent;data=json.loads((ROOT/'local/research/architecture-pivots/data.json').read_text())
    fixtures=[]
    for index,e in enumerate(data['dev']):
        x=np.memmap(e['inputs'],mode='r',dtype='<f4',shape=(e['rows'],525))
        base=ROOT/'local/research/architecture-pivots'/f'dev-{index:02d}'
        h=np.memmap(str(base)+'.history.bin',mode='r',dtype='<f4',shape=(e['rows'],16,32))
        pool=np.memmap(str(base)+'.pool.bin',mode='r',dtype='<f4',shape=(e['rows'],90))
        ix=np.linspace(0,e['rows']-1,32,dtype=int)
        fixtures.append(np.concatenate((x[ix],h[ix].reshape(-1,512),pool[ix]),axis=-1).astype('<f4'))
    fixtures=np.concatenate(fixtures);assert fixtures.shape[1]==INPUTS
    def calls(port,slot,expected,indices):
        conn=socket.create_connection(('127.0.0.1',port));conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        conn.sendall(slot.to_bytes(4,'little'));assert receive(conn,32)==expected
        result=[]
        try:
            for index in indices:
                conn.sendall(fixtures[index].tobytes());result.append((index,np.frombuffer(receive(conn,332),dtype='<f4').copy()))
        finally:conn.close()
        return result
    def parallel(port,slot,expected):
        result={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
            jobs=[executor.submit(calls,port,slot,expected,list(range(i,len(fixtures),14))) for i in range(14)]
            for future in jobs:result.update(future.result())
        return np.stack([result[i] for i in range(len(fixtures))])
    results={}
    for kind,port,slot,new_slot in [('entity',19531,2,12),('history',19532,3,13)]:
        expected=hashlib.sha256((here/kind/'model.pt').read_bytes()).digest()
        old=parallel(port,slot,expected);new=parallel(19536,new_slot,expected)
        results[kind]=dict(checkpoint_sha256=expected.hex(),positions=len(fixtures),
            float32_bit_exact=np.array_equal(old.view(np.uint32),new.view(np.uint32)),
            unequal_outputs=int(np.count_nonzero(old.view(np.uint32)!=new.view(np.uint32))),
            maximum_abs_error=float(np.max(np.abs(old-new))))
    (here/'batch-shape-parity.json').write_text(json.dumps(dict(batches=[32,16],workers=14,
        native_and_canonical=True,results=results),indent=2)+'\n')
    print(json.dumps(results))

if __name__=='__main__':main()
