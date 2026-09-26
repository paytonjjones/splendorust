#!/usr/bin/env python3
"""Check complete-turn exports against a pinned, unmodified external engine.

The reference is optional and is not a production dependency. Only Python's
standard library and the reference's rule modules are loaded. No ML packages.
"""
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_COMMIT = "95f84d2e6e839c0ef09ca97bdc3b3048a792fb0b"
COLORS = ["white", "blue", "green", "red", "black", "yellow"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_reference(path):
    revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    require(revision == REFERENCE_COMMIT, f"reference revision mismatch: {revision}")
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True)
    require(not dirty, "reference has tracked changes")
    license_text = (path / "LICENSE").read_text()
    require(license_text.startswith("MIT License\n"), "reference license mismatch")
    sys.path.insert(0, str(path / "src"))
    from splendor.splendor.splendor_model import Card, SplendorGameRule
    from splendor.splendor.splendor_utils import CARDS, NOBLES
    return Card, SplendorGameRule, CARDS, NOBLES, hashlib.sha256(license_text.encode()).hexdigest()


class Comparison:
    def __init__(self, path):
        Card, self.Rule, cards, nobles, self.license_hash = load_reference(path)
        rows = list(csv.DictReader((ROOT / "data/cards.csv").read_text().splitlines()))
        tuples = [(int(r["tier"]), r["bonus"], int(r["points"]), *(int(r[c]) for c in COLORS[:5])) for r in rows]
        external = {(tier, color, points, *(cost.get(c, 0) for c in COLORS[:5])): code
                    for code, (color, cost, tier, points) in cards.items()}
        require(len(external) == len(cards) == len(tuples) == 90 and set(external) == set(tuples), "card data differs")
        self.cards = []
        for key in tuples:
            code = external[key]
            color, cost, tier, points = cards[code]
            self.cards.append(Card(color, code, cost, tier - 1, points))
        self.card_ids = {card.code: i for i, card in enumerate(self.cards)}
        ours = [tuple(int(r[c]) for c in COLORS[:5]) for r in csv.DictReader((ROOT / "data/nobles.csv").read_text().splitlines())]
        external_nobles = {tuple(cost.get(c, 0) for c in COLORS[:5]): (code, cost) for code, cost in nobles}
        require(len(external_nobles) == len(nobles) == len(ours) == 10 and set(ours) == set(external_nobles), "noble data differs")
        self.nobles = [external_nobles[key] for key in ours]
        self.noble_ids = {n[0]: i for i, n in enumerate(self.nobles)}

    @staticmethod
    def gems(values):
        return dict(zip(COLORS, values))

    def hydrate(self, before, after):
        rule = self.Rule(len(before["players"]))
        state = rule.current_game_state
        state.board.gems = self.gems(before["bank"])
        state.board.nobles = [self.nobles[n] for n in before["nobles"]]
        state.board.dealt = [[None if c == 255 else self.cards[c] for c in before["market"][t*4:t*4+4]] for t in range(3)]
        used = set(before["market"]) - {255}
        for agent, p in zip(state.agents, before["players"]):
            agent.gems = self.gems(p["tokens"])
            agent.score = p["score"]
            agent.nobles = [self.nobles[n] for n in p["nobles"]]
            for c in p["owned"]:
                agent.cards[self.cards[c].colour].append(self.cards[c])
                used.add(c)
            for r in p["reserved"]:
                agent.cards["yellow"].append(self.cards[r["card"]])
                used.add(r["card"])
        state.board.decks = [[c for i, c in enumerate(self.cards) if i not in used and c.deck_id == t] for t in range(3)]
        require([len(d) for d in state.board.decks] == before["remaining"], "deck partition mismatch")
        # One turn draws at most one card. Align that exogenous draw; do not
        # claim RNG or hidden deck-order equivalence between implementations.
        for old, new in zip(before["market"], after["market"]):
            if old != new and new != 255:
                card = self.cards[new]
                deck = state.board.decks[card.deck_id]
                require(card in deck, "replacement card not in deck")
                deck.remove(card)
                deck.append(card)
        rule.current_agent_index = before["current"]
        return rule

    def normalized(self, rule):
        state = rule.current_game_state
        players = []
        for p in state.agents:
            players.append({"tokens": [p.gems[c] for c in COLORS], "score": p.score,
                            "bonuses": [len(p.cards[c]) for c in COLORS[:5]],
                            "owned": sorted(self.card_ids[card.code] for c in COLORS[:5] for card in p.cards[c]),
                            "reserved": [self.card_ids[c.code] for c in p.cards["yellow"]],
                            "nobles": sorted(self.noble_ids[n[0]] for n in p.nobles)})
        return {"players": players, "bank": [state.board.gems[c] for c in COLORS],
                "market": [255 if c is None else self.card_ids[c.code] for row in state.board.dealt for c in row],
                "remaining": [len(d) for d in state.board.decks],
                "nobles": sorted(self.noble_ids[n[0]] for n in state.board.nobles),
                "current": rule.current_agent_index, "terminal": rule.gameEnds()}

    def compare(self, case):
        before, after, actions = case["before"], case["after"], case["actions"]
        tag, payload = actions[0][0], actions[0][1:]
        if tag == 2:
            return "blind_reservation"
        rule = self.hydrate(before, after)
        p = before["players"][before["current"]]
        q = after["players"][before["current"]]
        gained = set(q["nobles"]) - set(p["nobles"])
        require(len(gained) <= 1, "multiple noble acquisitions")
        noble = self.nobles[next(iter(gained))] if gained else None
        action = {"noble": noble}
        if tag in (0, 1):
            collected = payload[:5] + [0] if tag == 0 else [0]*5 + [int(before["bank"][5] > 0)]
            returned = next((a[1:] for a in actions if a[0] == 6), [0]*6)
            action.update(type=("collect_same" if 2 in collected else "collect_diff") if tag == 0 else "reserve",
                          collected_gems={c: n for c, n in zip(COLORS, collected) if n},
                          returned_gems={c: n for c, n in zip(COLORS, returned) if n})
            if tag == 1:
                action.update(card=self.cards[before["market"][payload[0]]], card_position=divmod(payload[0], 4))
            if any(a and b for a, b in zip(collected, returned)):
                return "return_collected_color"
        elif tag in (3, 4):
            card_id = before["market"][payload[0]] if tag == 3 else p["reserved"][payload[0]]["card"]
            card = self.cards[card_id]
            if p["bonuses"][COLORS.index(card.colour)] == 7:
                return "seven_card_limit"
            payment = [a-b for a, b in zip(p["tokens"], q["tokens"])]
            paid = {c: n for c, n in zip(COLORS, payment) if n}
            if paid != rule.resources_sufficient(rule.current_game_state.agents[before["current"]], card.cost):
                return "optional_gold_payment"
            action.update(type="buy_available" if tag == 3 else "buy_reserve", card=card,
                          card_position=divmod(payload[0], 4) if tag == 3 else (3, payload[0]), returned_gems=paid)
        else:
            raise ValueError(f"unexpected main action {tag}")
        legal = rule.getLegalActions(rule.current_game_state, before["current"])
        require(action in legal, f"reference rejects shared action: {action}")
        rule.update(action)
        actual = self.normalized(rule)
        expected = {key: after[key] for key in actual if key != "players"}
        expected["players"] = [{**{k: v for k, v in p.items() if k != "reserved"},
                                "reserved": [r["card"] for r in p["reserved"]]} for p in after["players"]]
        # The Rust terminal state retains the last actor; reference update
        # advances to seat zero. Compare turn order before normal termination.
        if after["terminal"]:
            expected["current"] = 0
        require(actual == expected, f"successor mismatch: expected {expected}, got {actual}")
        return "matched"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=pathlib.Path, required=True)
    parser.add_argument("--cases", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    comparison = Comparison(args.reference.resolve())
    counts = collections.Counter()
    categories = collections.Counter()
    digest = hashlib.sha256()
    with args.cases.open("rb") as stream:
        first = next(stream)
        digest.update(first)
        metadata = json.loads(first)
        require(metadata["format"] == 1, "unsupported export format")
        for line_number, line in enumerate(stream, 2):
            digest.update(line)
            case = json.loads(line)
            try:
                result = comparison.compare(case)
            except (ValueError, KeyError, IndexError) as exc:
                raise ValueError(f"case line {line_number}, seed {case['seed']}, turn {case['before']['turns']}: {exc}") from exc
            counts[result] += 1
            if result == "matched":
                categories[f"players_{len(case['before']['players'])}"] += 1
                categories[f"action_{case['actions'][0][0]}"] += 1
                categories["terminal"] += int(case["after"]["terminal"])
                categories["noble"] += int(case["before"]["nobles"] != case["after"]["nobles"])
    require(counts["matched"] > 0, "no shared transitions were checked")
    report = {"reference": "https://github.com/roeey777/Splendor-AI", "commit": REFERENCE_COMMIT,
              "license": "MIT", "license_sha256": comparison.license_hash, "export": metadata,
              "cases_sha256": digest.hexdigest(),
              "harness_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              "exporter_sha256": hashlib.sha256((ROOT / "crates/splendor-arena/examples/parity_export.rs").read_bytes()).hexdigest(),
              "cards_matched": 90, "nobles_matched": 10,
              "cases": dict(counts), "matched_coverage": dict(categories),
              "scope": "Selected shared complete-turn transitions; aligned exogenous draws. Not full action-set, RNG, observation, or outcome parity."}
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
