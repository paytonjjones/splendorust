#!/usr/bin/env python3
"""Build the pinned AhinLendor extension in the ignored local checkout.

This uses the repository's pinned inference Python and its bundled pybind11
headers. It compiles and tests on CPU only. No upstream source is edited.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import sysconfig
import time

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / "local/strength/external/ahinlendor"
PIN = "96e6f2daff83147495826c4a2073dc3c9c856cc9"
PYTHON = ROOT / "local/strength/inference/bin/python"
RECEIPT_PATH = Path(__file__).with_name("build-receipt.json")
LOG_PATH = Path(__file__).with_name("build.log")
OUTPUT_DIR = UPSTREAM
SOURCE_FILES = (
    "game_logic.cpp", "state_encoder.cpp", "native_mcts.cpp",
    "native_endgame.cpp", "py_splendor.cpp",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, log, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    log.write("$ " + shlex.join(command) + "\n")
    log.flush()
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    log.write(result.stdout)
    if not result.stdout.endswith("\n"):
        log.write("\n")
    log.flush()
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {shlex.join(command)}")
    return result


def main() -> int:
    if not PYTHON.is_file():
        raise RuntimeError(f"pinned Python is missing: {PYTHON}")
    if not UPSTREAM.is_dir():
        raise RuntimeError(f"pinned upstream checkout is missing: {UPSTREAM}")
    head = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN:
        raise RuntimeError(f"wrong upstream commit: expected {PIN}, got {head}")
    tracked_changes = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    if tracked_changes:
        raise RuntimeError("upstream checkout has tracked changes; refusing build")

    old_receipt = json.loads(RECEIPT_PATH.read_text())
    expected_sources = old_receipt["upstream_source_sha256"]
    source_hashes = {}
    for relative, expected in expected_sources.items():
        source = UPSTREAM / relative
        actual = sha256(source)
        if actual != expected:
            raise RuntimeError(f"source hash mismatch for {relative}: {actual} != {expected}")
        source_hashes[relative] = actual
    for relative in SOURCE_FILES:
        if relative not in source_hashes:
            raise RuntimeError(f"build source is not pinned in receipt: {relative}")

    compiler = subprocess.check_output(["c++", "--version"], text=True).splitlines()[0]
    info = subprocess.check_output([
        str(PYTHON), "-c",
        "import json,sys,sysconfig,torch; print(json.dumps({'python':sys.version.split()[0], 'include':sysconfig.get_paths()['include'], 'ext_suffix':sysconfig.get_config_var('EXT_SUFFIX'), 'torch':torch.__version__, 'torch_include':torch.__path__[0]+'/include'}))",
    ], text=True)
    python_info = json.loads(info)
    suffix = python_info["ext_suffix"]
    if not suffix or not suffix.startswith(".cpython-") or not suffix.endswith(".so"):
        raise RuntimeError(f"unexpected extension suffix: {suffix!r}")
    python_include = Path(python_info["include"])
    torch_include = Path(python_info["torch_include"])
    if not (python_include / "Python.h").is_file() or not (torch_include / "pybind11/pybind11.h").is_file():
        raise RuntimeError("pinned Python/Torch headers are incomplete")
    output = OUTPUT_DIR / f"splendor_native{suffix}"
    command = [
        "c++", "-O3", "-DNDEBUG", "-std=c++17", "-fPIC", "-bundle",
        "-undefined", "dynamic_lookup", '-DSPLENDOR_BUILD_TYPE="Release"',
        "-DSPLENDOR_BUILD_OPTIMIZED=1", f"-I{python_include}", f"-I{torch_include}",
        *[str(UPSTREAM / source) for source in SOURCE_FILES], "-o", str(output),
    ]
    started = time.time()
    with LOG_PATH.open("w") as log:
        build_result = run(command, log=log)
        smoke = run([
            str(PYTHON), "-c",
            "import importlib.util,json,sys; from pathlib import Path; p=Path(sys.argv[1]); s=importlib.util.spec_from_file_location('splendor_native',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); e=m.NativeEnv(); r=e.reset(17); cards=m.list_standard_cards(); nobles=m.list_standard_nobles(); assert m.ACTION_DIM==69 and m.STATE_DIM==252 and len(cards)==90 and len(nobles)==10 and int(r.mask.sum())>0; f=lambda x,mask: (__import__('numpy').zeros((len(x),69),dtype='float32'),__import__('numpy').zeros((len(x),),dtype='float32')); q=e.run_ismcts(f,num_simulations=1,eval_batch_size=1,rng_seed=23); assert len(q.visit_probs)==69; print(json.dumps({'action_dim':m.ACTION_DIM,'state_dim':m.STATE_DIM,'standard_cards':len(cards),'standard_nobles':len(nobles),'reset_legal_actions':int(r.mask.sum()),'cpu_ismcts_simulations':1,'visit_probs_shape':list(q.visit_probs.shape),'build_type':m.BUILD_TYPE,'optimized':bool(m.BUILD_OPTIMIZED)}))",
            str(output),
        ], log=log)
    smoke_json = json.loads(smoke.stdout.strip().splitlines()[-1])
    if smoke_json["build_type"] != "Release" or not smoke_json["optimized"]:
        raise RuntimeError("extension build flags were not reflected by the module")
    receipt = {
        "schema": "ahinlendor-cpu-extension-build-v1",
        "upstream": {"path": "local/strength/external/ahinlendor", "commit": head, "dirty": False},
        "build": {
            "command": shlex.join(command),
            "compiler": compiler,
            "python": python_info["python"],
            "python_path": "local/strength/inference/bin/python",
            "python_include": str(python_include),
            "torch_version": python_info["torch"],
            "torch_pybind_headers": str(torch_include / "pybind11"),
            "output": str(output.relative_to(ROOT)),
            "output_sha256": sha256(output),
            "optimized": True,
            "gpu_inference_run": False,
            "elapsed_seconds": round(time.time() - started, 3),
            "build_exit_code": build_result.returncode,
        },
        "upstream_source_sha256": source_hashes,
        "smoke": {**smoke_json, "real_model_checkpoint_tested": False},
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(RECEIPT_PATH), "output": str(output), "sha256": receipt["build"]["output_sha256"], "smoke": receipt["smoke"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        raise
