#!/usr/bin/env python3
"""Record the immutable information experiment before outcome runs."""
import json
import platform
import subprocess
from pathlib import Path
from boundary import ROOT, sha
from upstream import SOURCE, PIN

BASE = Path(__file__).resolve().parent

def main():
    output = BASE/'freeze.json'
    if output.exists(): raise RuntimeError('freeze already exists')
    actual = subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    assert actual == PIN
    assert not subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain','--untracked-files=no'],text=True).strip()
    files = [ROOT/'Cargo.toml',ROOT/'Cargo.lock',ROOT/'rust-toolchain.toml',ROOT/'benchmarks/strength/requirements.txt',
             ROOT/'research/e81/model/model.bin',SOURCE/'splendor/pretrained_2players.pt']
    files += list((ROOT/'crates').rglob('*.rs')) + list((ROOT/'crates').rglob('Cargo.toml'))
    files += list(BASE.glob('*.py'))
    files += [ROOT/'benchmarks/strength/native'/name for name in ['upstream.py','run.py','validate.py']]
    files += [ROOT/'target/release/examples'/name for name in ['strength_worker','native_policy_worker','privileged_native_worker','native_rules_probe']]
    upstream_files = subprocess.check_output(['git','-C',str(SOURCE),'ls-files','-z']).decode().split('\0')
    record = dict(schema='information-fair-freeze-v1',
        revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        host=platform.platform(),machine=platform.machine(),
        rustc=subprocess.check_output(['rustc','-Vv'],text=True),
        python=__import__('sys').version,
        packages=subprocess.check_output([__import__('sys').executable,'-m','pip','freeze'],text=True).splitlines(),
        upstream_revision=PIN,upstream_files={name:sha(SOURCE/name) for name in upstream_files if name},
        files={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files))},
        endpoint=dict(model='research/e81/model/model.bin',search='gumbel',iterations=128,depth=16,world_pool=3,
            cpuct=.4,fpu_reduction=.02965,uniform_prior=0,root_only=False,root_noise=0),
        schedules=dict(screen=dict(games_per_arm=2000,master=4900000000,workers=8),
                       confirmation=dict(games_per_arm=20000,master=4910000000,workers=8)))
    output.write_text(json.dumps(record,indent=2)+'\n')
    print('Frozen',record['revision'],len(record['files']),'files')

if __name__=='__main__': main()
