"""Inventory retained research artifacts without changing or moving them."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "ARTIFACTS.json"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    entries = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path == OUTPUT or "__pycache__" in path.parts:
            continue
        stat = path.stat()
        entries.append(dict(path=str(path.relative_to(HERE)), bytes=stat.st_size,
                            sha256=digest(path)))
        assert path.stat().st_size == stat.st_size, f"Artifact changed: {path}"
    result = dict(scope="Retained study artifacts; external corpus locations are in the data registries and frozen Entity handoff",
                  directory=str(HERE), files=entries,
                  total_bytes=sum(item["bytes"] for item in entries))
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(files=len(entries), total_bytes=result["total_bytes"])))


if __name__ == "__main__":
    main()
