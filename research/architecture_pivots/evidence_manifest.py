"""Bind canonical gates to actual model files and frozen executables."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity(path):
    data=path.read_bytes();result=dict(path=str(path),sha256=sha(path),bytes=len(data))
    if data.startswith(b'SPREMOTE'):
        endpoint,slot,digest,history=data[8:].decode().splitlines()
        assert history in ('0','1','2')
        result.update(runtime='tensor-service',endpoint=endpoint,slot=int(slot),checkpoint_sha256=digest,
            public_history=history!='0',history_version=int(history))
    else:result['runtime']='native Rust'
    return result
def main():
    champion=ROOT/'research/e81/model/model.bin'
    assert sha(champion)=='e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8'
    mapping={'small-gate':HERE/'small/model.bin','capacity-gate':HERE/'capacity/native-model.bin','entity-gate':HERE/'entity/model.bin','small-cold-gate':HERE/'small-cold-mps/model.bin'}
    for name,model in mapping.items():
        directory=HERE/name
        if not (directory/'build.json').exists():continue
        build=json.loads((directory/'build.json').read_text());binary=directory/'splendor.bin'
        if not binary.exists():
            import shutil
            files=[Path(build['executable']),*list((ROOT/'target/release/deps').glob('splendor-*'))]
            matches=[p for p in files if p.is_file() and p.stat().st_mode&0o111 and sha(p)==build['binary_sha256']]
            assert matches,name
            shutil.copy2(matches[0],binary)
        assert sha(binary)==build['binary_sha256']
        result=dict(candidate=identity(model),baseline=identity(champion),binary_sha256=sha(binary),environment={'SPLENDOR_CANDIDATE_MODEL':str(model),'SPLENDOR_BEST_MODEL':str(champion)},script_sha256=sha(Path(__file__)))
        if result['candidate']['runtime']=='tensor-service':
            ready=json.loads((HERE/'entity-service-resume.log').read_text().splitlines()[0]);result['service']=ready
            assert ready['models'][str(result['candidate']['slot'])]['sha256']==result['candidate']['checkpoint_sha256']
        (directory/'inference-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
