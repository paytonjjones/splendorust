#!/usr/bin/env python3
"""Recover the pre-change core and unchanged timed loop in an isolated snapshot."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASE = "534cd4097d26a196039b020828c597765a31f619"
OUT = ROOT / "local/research/engine-throughput/baseline-source"
ORIGINAL_SHA = "0fbe3745af4034b2a1ab7003212421621e342e478bbd70b50f252cb11bd9650a"


def main():
    original = (ROOT / "crates/splendor-arena/examples/engine_trajectory.rs").read_text()
    original = original.replace(".legal_actions_reference(", ".legal_actions(")
    if hashlib.sha256(original.encode()).hexdigest() != ORIGINAL_SHA:
        raise SystemExit("original trajectory source no longer matches its receipt")
    archive = subprocess.check_output(["git", "archive", BASE, "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "crates"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        if not OUT.exists():
            OUT.mkdir(parents=True)
            source.extractall(OUT, filter="data")
        else:
            for member in source.getmembers():
                if not member.isfile() or member.name == "crates/splendor-arena/Cargo.toml":
                    continue
                path = OUT / member.name
                if not path.exists() or path.read_bytes() != source.extractfile(member).read():
                    raise SystemExit(f"baseline source differs from pinned commit: {member.name}")
    # These edits change only repeat configuration and per-trace coverage gating.
    # The original timed loop, enumeration, membership and checked apply remain.
    text = original.replace("const REPLAY_GAMES: usize = 10_000;", "")
    text = text.replace("    let mut setup_rng = Rng::new(seed);", """    let replay_games = args.next().as_deref().unwrap_or("10000").parse::<usize>().unwrap();
    let repeats = args.next().as_deref().unwrap_or("3").parse::<usize>().unwrap();
    let mut setup_rng = Rng::new(seed);""")
    start = text.index('    if status == "complete"\n        && (')
    end = text.index("    writeln!(", start)
    text = text[:start] + text[end:]
    text = text.replace("REPLAY_GAMES", "replay_games").replace("for repeat in 0..3", "for repeat in 0..repeats")
    (OUT / "crates/splendor-arena/examples/engine_baseline.rs").write_text(text)
    manifest = OUT / "crates/splendor-arena/Cargo.toml"
    base_manifest = subprocess.check_output(["git", "show", f"{BASE}:crates/splendor-arena/Cargo.toml"], cwd=ROOT).decode()
    manifest.write_text(base_manifest + '\n[[example]]\nname = "engine_baseline"\nrequired-features = ["benchmark-compat"]\n')
    hashes = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(OUT.rglob("*")) if p.is_file() and p.suffix in {".rs", ".toml", ".lock", ".bin"}}
    (OUT.parent / "baseline-source.json").write_text(json.dumps({"base_commit": BASE, "original_trajectory_sha256": ORIGINAL_SHA,
        "scope": "original 7-byte Action, original core and timed loop; configurable repeats, per-trace coverage gate relaxed",
        "sources": hashes}, indent=2) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
