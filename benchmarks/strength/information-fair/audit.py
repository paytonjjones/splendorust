#!/usr/bin/env python3
"""Audit frozen runtime, lossless histories, replay evidence and paired summaries."""
import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from boundary import ROOT, ARMS, sha
from upstream import SOURCE
from summarize import summarize

BASE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['screen','confirmation'])
    args=parser.parse_args()
    stages=[args.stage] if args.stage else ['screen','confirmation']
    freeze=json.loads((BASE/'freeze.json').read_text())
    for name, expected in freeze['files'].items(): assert sha(ROOT/name)==expected, ('changed frozen file',name)
    for name, expected in freeze['upstream_files'].items(): assert sha(SOURCE/name)==expected, ('changed upstream file',name)
    # Keep every pre-existing strength benchmark and all canonical rules intact.
    changed = subprocess.check_output([
        "git", "-C", str(ROOT), "diff", "--name-only", "2f627b0", "--",
        "benchmarks/strength", "crates/splendor-core", ".github",
    ], text=True).splitlines()
    assert all(name.startswith("benchmarks/strength/information-fair/") for name in changed), changed
    counts=[]
    for stage in stages:
        for arm in ARMS:
            directory=BASE/stage/arm
            manifest=json.loads((directory/'archives.json').read_text())
            with (directory/'games.jsonl').open() as raw:
                meta=json.loads(next(raw))
            schedule=freeze['schedules'][stage]
            assert meta['games']==schedule['games_per_arm']
            assert meta['master']==schedule['master'] and meta['offset_block']==0
            assert meta['workers']==schedule['workers']
            for key,value in freeze['endpoint'].items():
                if key in ['model','root_noise']: continue
                assert meta[key]==value, ('changed endpoint',key)
            assert meta['gumbel_config']==dict(max_considered=16,cvisit=50,cscale=.1,root_noise=0)
            assert meta['external_config']==dict(numMCTSSims=800,fpu=.0593,universes=3,
                cpuct=.8,prob_fullMCTS=1.,forced_playouts=False,no_mem_optim=False)
            assert meta['model_sha256']==freeze['files']['research/e81/model/model.bin']
            assert meta['upstream_revision']==freeze['upstream_revision']
            assert meta['upstream_checkpoint_sha256']==freeze['upstream_files']['splendor/pretrained_2players.pt']
            binary='privileged_native_worker' if arm=='privileged-sr' else 'native_policy_worker'
            assert meta['policy_binary_sha256']==freeze['files']['target/release/examples/'+binary]
            for name,expected in meta['source_sha256'].items():
                assert expected==freeze['files'][name], ('unfrozen execution source',name)
            assert meta['information_arm']==arm
            expected_observation='native-exact-unordered-v1' if arm=='privileged-sr' else 'native-public-history-v1'
            assert meta['observation_profile']==expected_observation
            digest=hashlib.sha256(); lines=0
            for chunk in manifest['chunks']:
                path=directory/chunk['file'];assert sha(path)==chunk['archive_sha256']
                data=gzip.decompress(path.read_bytes());assert hashlib.sha256(data).hexdigest()==chunk['raw_sha256']
                assert len(data)==chunk['raw_bytes'];digest.update(data);lines+=data.count(b'\n')
            assert digest.hexdigest()==manifest['raw_sha256'] and lines==manifest['games']+1
            replay=json.loads((directory/'replay.json').read_text())
            assert replay['raw_sha256']==manifest['raw_sha256'] and replay['checked_games']==manifest['games']
            counts.append(dict(stage=stage,arm=arm,games=manifest['games'],transitions=replay['checked_transitions'],raw_sha256=manifest['raw_sha256']))
        # Retained ignored originals support a fresh exact summary rerun.
        result=summarize(BASE/stage)
        assert result==json.loads((BASE/stage/'summary.json').read_text())
        assert all(r['statuses']=={'complete':freeze['schedules'][stage]['games_per_arm']} for r in result['arms'].values())
    result=dict(status='passed',frozen_revision=freeze['revision'],schedules=counts,
        games=sum(r['games'] for r in counts),transitions=sum(r['transitions'] for r in counts),
        original_benchmarks_and_canonical_rules_unchanged=True,fixed_protocol_checked=True,scope='Original benchmarks/core preserved; exact seed schedules and all fixed settings checked; frozen code/binaries/models/upstream; lossless archive hashes; complete replay counts; exact rerun of matched statistical summaries.')
    output=BASE/(f'{args.stage}-audit.json' if args.stage else 'final-audit.json')
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
