"""Compile fixed-observation cost control with Cargo-selected libraries."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import sha
out=ROOT/'research/e95';libs={}
for line in (ROOT/'local/research/e95/cargo-build.jsonl').read_text().splitlines():
 try:d=json.loads(line)
 except ValueError:continue
 if d.get('reason')=='compiler-artifact' and d['target']['name'] in ['splendor_agents','splendor_core','serde_json']:
  libs[d['target']['name']]=next(p for p in d['filenames'] if p.endswith('.rlib'))
assert len(libs)==3
cmd=['rustc','--edition=2024','-O','-D','warnings','-C','lto=thin','-C','codegen-units=1',str(out/'cost.rs'),'-L',f'dependency={ROOT}/local/research/flywheel-target/release/deps']
for name,path in libs.items():cmd+=['--extern',f'{name}={path}']
cmd+=['-o',str(ROOT/'local/research/e95/cost')]
with (out/'cost-build.log').open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
(out/'cost-build.json').write_text(json.dumps(dict(command=cmd,files={str(p):sha(p) for p in [out/'cost.rs',ROOT/'local/research/e95/cost',*libs.values()]},toolchain=subprocess.check_output(['rustc','--version'],text=True).strip()),indent=2)+'\n')
