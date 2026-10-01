import json,subprocess,hashlib,os
from pathlib import Path
root=Path(__file__).resolve().parents[2];os.chdir(root);out=root/'research/e90';libs={}
for line in open('research/e89/gate/cargo-build.jsonl'):
 try:d=json.loads(line)
 except:continue
 if d.get('reason')=='compiler-artifact' and d['target']['name'] in ['splendor_agents','splendor_core','serde_json','rayon']:
  libs[d['target']['name']]=next(p for p in d['filenames'] if p.endswith('.rlib'))
cmd=['rustc','--edition=2024','-O','-D','warnings','-C','lto=thin','-C','codegen-units=1','research/e90/probe.rs','-L','dependency=local/research/flywheel-target/release/deps']
for k,v in libs.items():cmd+=['--extern',f'{k}={v}']
cmd+=['-o','local/research/e90/probe']
with (out/'build.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
(out/'build.json').write_text(json.dumps(dict(command=cmd,files={p:sha(p) for p in ['research/e90/probe.rs','local/research/e90/probe','research/e88/model/model.bin',*libs.values()]},toolchain=subprocess.check_output(['rustc','--version'],text=True).strip()),indent=2)+'\n')
env=os.environ.copy();env['SPLENDOR_BEST_MODEL']=str(root/'research/e88/model/model.bin')
with (out/'raw.json').open('w') as f:subprocess.run(['local/research/e90/probe'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
