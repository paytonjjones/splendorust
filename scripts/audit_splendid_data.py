#!/usr/bin/env python3
"""Audit the pinned csmith/splendid data without installing its dependencies."""
import collections
import csv
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = "52b017c96d0b010fe228b8284b4646da505545e2"
LICENSE_SHA = "c84dbce62ceda5d536dc48641af1970726c960609b63f2ae2709d6125433f838"
COLORS = ["white", "blue", "green", "red", "black"]
GEMS = ["diamond", "sapphire", "emerald", "ruby", "onyx"]


def main():
    checkout = pathlib.Path(sys.argv[1]).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()
    if git("rev-parse", "HEAD") != COMMIT or git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("reference must be a clean tracked checkout at the pinned commit")
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(checkout / "LICENCE") != LICENSE_SHA:
        raise ValueError("reference license hash differs")
    paths = [checkout / "src/games/splendid/data" / (name + ".js") for name in ("cards", "nobles")]
    code = "\n".join(f"import {name} from {json.dumps(path.as_uri())};" for name, path in zip(("cards", "nobles"), paths))
    code += "\nconsole.log(JSON.stringify({cards,nobles}));"
    data = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", code], text=True))
    with (ROOT / "data/cards.csv").open() as stream:
        cards = collections.Counter((int(r["tier"]), r["bonus"], int(r["points"]), *(int(r[c]) for c in COLORS)) for r in csv.DictReader(stream))
    with (ROOT / "data/nobles.csv").open() as stream:
        nobles = collections.Counter(tuple(int(r[c]) for c in COLORS) for r in csv.DictReader(stream))
    other_cards = collections.Counter((r["level"], COLORS[GEMS.index(r["bonus"])], r["points"], *(r["cost"].get(c, 0) for c in GEMS)) for r in data["cards"])
    other_nobles = collections.Counter(tuple(r["cost"].get(c, 0) for c in GEMS) for r in data["nobles"])
    def compare(local, reference):
        return {"local_count": local.total(), "reference_count": reference.total(),
                "shared_count": (local & reference).total(),
                "missing_from_reference": sorted((local - reference).elements()),
                "extra_in_reference": sorted((reference - local).elements())}
    print(json.dumps({"repository": "https://github.com/csmith/splendid", "commit": COMMIT,
        "license": "MIT", "license_sha256": LICENSE_SHA,
        "script_sha256": sha(pathlib.Path(__file__)),
        "files_sha256": {str(p.relative_to(checkout)): sha(p) for p in paths},
        "local_files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / "data/cards.csv", ROOT / "data/nobles.csv"]},
        "color_order": COLORS, "card_tuple": "tier, bonus, points, five costs",
        "noble_tuple": "five requirements only; no prestige comparison",
        "cards": compare(cards, other_cards), "nobles": compare(nobles, other_nobles),
        "decision": "Reject as a full standard-game parity baseline; no transition parity tested."}, indent=2))


if __name__ == "__main__":
    main()
