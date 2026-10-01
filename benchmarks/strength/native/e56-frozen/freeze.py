#!/usr/bin/env python3
"""Save immutable source/model/runtime provenance before strength schedules."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from upstream import ROOT,SOURCE,PIN,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    python=ROOT/'local/strength/inference/bin/python'
    upstream_files=subprocess.check_output(['git','-C',str(SOURCE),'ls-files'],text=True).splitlines()
    rust_files=[ROOT/p for p in ['crates/splendor-agents/src/environment.rs','crates/splendor-agents/src/native_environment.rs','crates/splendor-agents/src/neural_search.rs','crates/splendor-agents/src/lib.rs','crates/splendor-arena/examples/native_policy_worker.rs','crates/splendor-arena/examples/native_rules_probe.rs','crates/splendor-arena/examples/native_wire/mod.rs','Cargo.lock','rust-toolchain.toml']]
    canonical_paths=['crates/splendor-core','crates/splendor-agents/src/transfer.rs','research','benchmarks/adapters/alphazero_strength.py','benchmarks/strength/run.py','benchmarks/strength/REPORT.md','benchmarks/strength/PROFILES.md','benchmarks/strength/results']
    assert not subprocess.check_output(['git','-C',str(ROOT),'diff','d9d4e4d','--',*canonical_paths],text=True).strip(), 'protected files changed'
    actual=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip();assert actual==PIN
    assert not subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain','--untracked-files=no'],text=True).strip()
    models=[ROOT/'research/e56/model/model.bin',ROOT/'research/e56/model/model.pt',SOURCE/'splendor/pretrained_2players.pt']
    binaries=[ROOT/'target/release/examples'/name for name in ['native_policy_worker','native_rules_probe','strength_worker','strength_replay']]
    files={str(path.relative_to(ROOT)):sha(path) for path in rust_files+models+binaries}
    manifest=dict(profile='alphazero-native-32a27ac-v1',base_revision='d9d4e4d',
        repository_revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        upstream_revision=PIN,upstream_file_sha256={path:sha(SOURCE/path) for path in upstream_files if (SOURCE/path).is_file()},
        source_model_binary_sha256=files,
        harness_sha256={str(path.relative_to(ROOT)):sha(path) for path in Path(__file__).parent.glob('*.py')},
        rust=subprocess.check_output(['rustc','-Vv'],text=True).splitlines(),
        python=subprocess.check_output([str(python),'-V'],text=True).strip(),
        packages=subprocess.check_output(['uv','pip','freeze','--python',str(python)],text=True).splitlines(),
        protected_files_unchanged=True,canonical_feature_contract='ID-sorted nobles, frozen 392/81/2 model',
        primary=dict(model_sha256=files['research/e56/model/model.bin'],iterations=128,depth=16,world_pool=3,cpuct=.4,fpu_reduction=.02965,uniform_prior=0),
        external=dict(numMCTSSims=800,cpuct=.8,fpu=.0593,universes=3,prob_fullMCTS=1.,forced_playouts=False,no_mem_optim=False),
        timing_caveat='Concurrent main learning job observed on the same host; no clean isolated runtime or equal-compute claim.')
    a.output.write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
