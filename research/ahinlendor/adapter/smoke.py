"""CPU-only no-weight end-to-end adapter smoke; this does not measure strength."""
from __future__ import annotations

import importlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from adapter import (
    AdapterError, BoardView, CanonicalAction, ReservedSlot,
    canonical_payment_for_ahin, complete_return, map_action,
)
from hydration import build_load_state_payload

ROOT = Path(__file__).resolve().parents[3]
AHIN = ROOT / "local/strength/external/ahinlendor"
REFEREE = ROOT / "local/research/ahinlendor/target-adapter/release/examples/ahin_referee"
TURN_LIMIT_SECONDS = 20.0
SMOKE_SEED = 1_704_200_137
AHIN_PIN = "96e6f2daff83147495826c4a2073dc3c9c856cc9"
REFEREE_SOURCE = ROOT / "crates/splendor-arena/examples/ahin_referee.rs"
CORE_SOURCE = ROOT / "crates/splendor-core/src/lib.rs"
ARENA_MANIFEST = ROOT / "crates/splendor-arena/Cargo.toml"
CARGO_LOCK = ROOT / "Cargo.lock"
ADAPTER_SOURCES = tuple(Path(__file__).parent / name for name in
                        ("adapter.py", "hydration.py", "smoke.py"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _provenance() -> dict[str, Any]:
    upstream = subprocess.run(
        ["git", "-C", str(AHIN), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if upstream != AHIN_PIN:
        raise RuntimeError(f"Ahin source pin changed: expected {AHIN_PIN}, got {upstream}")
    sources = (REFEREE_SOURCE, CORE_SOURCE, ARENA_MANIFEST, CARGO_LOCK, *ADAPTER_SOURCES)
    return {
        "upstream": {"path": str(AHIN), "commit": upstream},
        "referee_binary": {"path": str(REFEREE), "sha256": _sha256(REFEREE)},
        "build": {
            "profile": "release",
            "command": "CARGO_TARGET_DIR=local/research/ahinlendor/target-adapter cargo build --release --locked -p splendor-arena --example ahin_referee",
            "cargo_lock_sha256": _sha256(CARGO_LOCK),
            "target_dir": str(ROOT / "local/research/ahinlendor/target-adapter"),
        },
        "source_sha256": {str(path.relative_to(ROOT)): _sha256(path) for path in sources},
    }


def _canonical_actions(observation: dict[str, Any]) -> set[CanonicalAction]:
    return {
        CanonicalAction(str(row["kind"]), tuple(int(v) for v in row["values"]))
        for row in observation["legal_actions"]
    }


def _board_view(observation: dict[str, Any]) -> BoardView:
    viewer = int(observation["viewer"])
    own = observation["players"][viewer]
    opponent = observation["players"][1 - viewer]
    return BoardView(
        tuple(observation["market"]),
        tuple(int(slot["card_id"]) for slot in own["reserved"]),
        tuple(ReservedSlot(slot["card_id"], int(slot["tier"]), bool(slot["public"]))
              for slot in opponent["reserved"]),
        tuple(int(n) for n in observation["nobles"]),
        tuple(int(n) for n in own["tokens"]),
    )


def _choose_ahin_action(env: Any, native_state: Any, observation: dict[str, Any],
                        card_by_id: dict[int, dict[str, Any]]) -> tuple[CanonicalAction, set[str]]:
    legal = _canonical_actions(observation)
    phase = observation["phase"]
    if phase == "payment":
        card_id = observation.get("pending_card_id")
        if card_id is None:
            raise AdapterError("canonical payment prompt lacks its public card ID")
        card = card_by_id[int(card_id) + 1]
        player = observation["players"][int(observation["viewer"])]
        cost = tuple(int(card["cost"][color]) for color in ("white", "blue", "green", "red", "black"))
        payment = canonical_payment_for_ahin(
            cost, tuple(map(int, player["bonuses"])), tuple(map(int, player["tokens"])))
        if payment not in legal:
            raise AdapterError(f"Ahin automatic payment is not canonical-legal: {payment}")
        return payment, {"payment"}

    if phase not in {"main", "return", "noble"}:
        raise AdapterError(f"unsupported canonical phase {phase!r}")
    payload = build_load_state_payload(observation, sample_seed=0xA11 + int(observation["decision_id"]))
    native_state = env.load_state(payload)
    mask = native_state.mask
    indices = [i for i, legal_flag in enumerate(mask) if bool(legal_flag)]
    if not indices:
        raise AdapterError("Ahin native environment has no legal root action")
    view = _board_view(observation)

    if phase == "return":
        selected: list[int] = []
        for _ in range(sum(view.own_tokens) - 10):
            state = env.get_state()
            choices = [i for i in range(61, 66) if bool(state.mask[i])]
            if not choices:
                raise AdapterError("Ahin cannot complete canonical return bundle")
            intent = map_action(choices[0], view, legal)
            if intent.kind != "return_token":
                raise AdapterError("return index did not map to a token intent")
            selected.append(intent.values[0])
            env.step(choices[0])
        action = complete_return(view, selected, legal)
        return action, {"return"}

    if phase == "noble":
        candidates = [i for i in indices if 66 <= i <= 68]
    else:
        own = observation["players"][int(observation["viewer"])]
        reserve_count = len(own["reserved"])
        # Force legal blind reserves early so the private-reservation path is
        # exercised. The selected identity is never read from the referee.
        candidates = [i for i in indices if 27 <= i <= 29] if reserve_count < 3 else []
        if not candidates:
            candidates = [i for i in indices if 0 <= i <= 14]
        if not candidates:
            candidates = [i for i in indices if 30 <= i <= 59]
        if not candidates:
            candidates = [i for i in indices if 15 <= i <= 29]
    if not candidates:
        raise AdapterError("no compatible scripted Ahin action at this canonical state")
    index = min(candidates)
    action = map_action(index, view, legal)
    if action.kind == "return_token":
        raise AdapterError("single return intent escaped bundle handling")
    categories = {action.kind}
    return action, categories


def run_smoke(max_decisions: int = 1200, seed: int = SMOKE_SEED) -> dict[str, Any]:
    if not REFEREE.exists():
        raise FileNotFoundError(f"build the isolated referee first: {REFEREE}")
    sys.path.insert(0, str(AHIN))
    native = importlib.import_module("splendor_native")
    env = native.NativeEnv()
    card_by_id = {int(card["id"]): dict(card) for card in native.list_standard_cards()}
    process = subprocess.Popen(
        [str(REFEREE), "--seed", str(seed), "--max-decisions", str(max_decisions)],
        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    categories: set[str] = set()
    phases: set[str] = set()
    sampled_hidden = False
    previous_turn: tuple[int, int] | None = None
    turn_started = time.monotonic()
    try:
        assert process.stdin is not None and process.stdout is not None
        while True:
            raw = process.stdout.readline()
            if not raw:
                raise RuntimeError("referee stopped before returning a final status")
            record = json.loads(raw)
            if record.get("schema") == "ahin-referee-result-v1":
                result = record
                break
            if record.get("schema") != "ahin-referee-observation-v1":
                raise RuntimeError(f"unknown referee record schema: {record.get('schema')}")
            if record["terminal"] is not False:
                raise RuntimeError("referee sent a terminal observation instead of a result")
            key = (int(record["turn_id"]), int(record["viewer"]))
            if key != previous_turn:
                previous_turn = key
                turn_started = time.monotonic()
            if time.monotonic() - turn_started > TURN_LIMIT_SECONDS:
                raise TimeoutError("single player turn exceeded the cumulative 20-second smoke guard")
            phases.add(record["phase"])
            sampled_hidden |= any(slot["card_id"] is None
                                  for player in record["players"] for slot in player["reserved"])
            action, used = _choose_ahin_action(env, None, record, card_by_id)
            # This is a post-call guard, not a preemptive timeout. A blocked
            # referee read or action chooser can run beyond the limit first.
            if time.monotonic() - turn_started > TURN_LIMIT_SECONDS:
                raise TimeoutError("single player turn exceeded the cumulative 20-second smoke guard")
            categories.update(used)
            process.stdin.write(json.dumps({"action": {"kind": action.kind,
                                                       "values": list(action.values)}}) + "\n")
            process.stdin.flush()
        code = process.wait(timeout=3)
        if code != 0:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"referee exited {code}: {stderr}")
        return {
            "schema": "ahin-adapter-smoke-v1",
            "strength_claim": False,
            "mode": "scripted legal actions; no weights or search",
            "seed": seed,
            "decisions": result["decisions"],
            "status": result["status"],
            "phases_seen": sorted(phases),
            "canonical_action_categories": sorted(categories),
            "saw_hidden_reservation_redaction": sampled_hidden,
            "turn_guard": {
                "seconds": TURN_LIMIT_SECONDS,
                "scope": "one canonical player turn across all subdecisions",
                "preemptive": False,
                "limitation": "blocking referee reads or action selection can exceed the limit before the post-call check",
            },
            "provenance": _provenance(),
        }
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SMOKE_SEED)
    parser.add_argument("--max-decisions", type=int, default=1200)
    args = parser.parse_args()
    print(json.dumps(run_smoke(args.max_decisions, args.seed), indent=2))
