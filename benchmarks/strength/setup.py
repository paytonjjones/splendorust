#!/usr/bin/env python3
"""Fetch only the three fixed sources and build isolated strength workers."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PINS={'alphazero':('https://github.com/lyquentxy/splendor.git','32a27ac1f85d5de2766cc5f60c2bf04e557f7836'),
      'schuber6':('https://github.com/schuber6/Splendor-Bot.git','1a3713b95889e05f70c00e806698a6e8d59078f1'),
      'seal256':('https://github.com/seal256/splendor.git','263abc066c563a1c89dba4bdc408446a20ad9d1d')}
def run(command,**kw):subprocess.run(list(map(str,command)),check=True,**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    base=ROOT/'local/strength';base.mkdir(parents=True,exist_ok=True)
    refs={}
    for name,(url,rev) in PINS.items():
        dest=base/'external'/name
        if not dest.exists():run(['git','clone',url,dest])
        actual=subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
        if actual!=rev:
            if subprocess.check_output(['git','-C',str(dest),'status','--porcelain'],text=True).strip():raise RuntimeError('dirty external source')
            run(['git','-C',dest,'checkout','--detach',rev])
        refs[name]=dest
    dest=refs['seal256'];header=dest/'src/splendor.h'
    original=subprocess.check_output(['git','-C',str(dest),'show',PINS['seal256'][1]+':src/splendor.h'],text=True)
    patched=original.replace('private:\n    std::pair<bool, ActionError> verify_action(const int action_id) const;',
        'public: // Benchmark interface only: expose the unchanged validation method.\n    std::pair<bool, ActionError> verify_action(const int action_id) const;\nprivate:')
    if header.read_text() not in (original,patched):raise RuntimeError('unknown seal256 header patch')
    header.write_text(patched)
    for name,dest in refs.items():
        dirty=subprocess.check_output(['git','-C',str(dest),'diff','--name-only'],text=True).splitlines()
        if dirty!=(['src/splendor.h'] if name=='seal256' else []):raise RuntimeError('unknown source patch: '+name)
    run(['uv','venv','--python','3.11.13',base/'inference'])
    python=base/'inference/bin/python'
    run(['uv','pip','install','--python',python,'-r',ROOT/'benchmarks/strength/requirements.txt'])
    run(['cargo','build','--release','--locked','-p','splendor-arena','--example','strength_worker','--example','strength_replay'],cwd=ROOT)
    for script,binary in [('build_seal256.sh','seal256-native-strength'),('build_seal256_adapter.sh','seal256-adapter')]:
        run(['bash',ROOT/'benchmarks/strength'/script,refs['seal256'],base/binary])
    run(['clang++','-O3','-DNDEBUG','-std=c++20','-pthread','-I'+str(refs['seal256']/'src'),refs['seal256']/'src/splendor.cpp',refs['seal256']/'src/game_state.cpp',ROOT/'benchmarks/adapters/seal256_replay.cpp','-o',base/'seal256-replay'])
    manifest={'pins':{name:{'url':url,'revision':rev} for name,(url,rev) in PINS.items()},
              'binaries':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'target/release/examples/strength_worker',python,base/'seal256-native-strength',base/'seal256-adapter',base/'seal256-replay',ROOT/'target/release/examples/strength_replay']},
              'checkpoints':{str(p.relative_to(ROOT)):sha(p) for p in list((refs['alphazero']/'splendor').glob('pretrained_*players.pt'))+list((refs['schuber6']/'Saved Weights').iterdir())},
              'compiler':subprocess.check_output(['clang++','--version'],text=True).splitlines(),
              'rust':subprocess.check_output(['rustc','-Vv'],text=True).splitlines(),
              'python':subprocess.check_output([str(python),'-V'],text=True).strip(),
              'requirements_sha256':sha(ROOT/'benchmarks/strength/requirements.txt'),
              'source_patch':'seal256: public access for unchanged verify_action only'}
    (ROOT/'benchmarks/strength/build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
