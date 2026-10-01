import json,hashlib
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
paths=['research/e80/compare.rs','local/research/e80-compare','local/research/flywheel-target/release/deps/libsplendor_agents-1a03f936d2dec845.rlib','research/e68/model/model.bin']
Path('research/e80/build.json').write_text(json.dumps(dict(files={p:sha(p) for p in paths},seed='core Rng(master4530000000) emits1000 setup seeds; policy seeds4531000000+2*block+seat independent of setup RNG; both rotations per block',threads=14,iterations=800,depth=16,rule='complete paired target-execution diagnostic; no promotion'),indent=2)+'\n')
