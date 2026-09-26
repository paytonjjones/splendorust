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


class WorkloadSequence:
    """Check full exporter schedules and continuity, not external trajectory parity."""

    def __init__(self, metadata):
        self.games = metadata.get("games_per_player_count")
        self.seed = metadata.get("seed")
        self.index = 0
        self.previous = None
        self.cases = 0
        if self.games is None:
            require(type(metadata.get("depletion_tier")) is int and 0 <= metadata["depletion_tier"] <= 2,
                    "missing full-game schedule or valid boundary-history scope")
        else:
            require("depletion_tier" not in metadata, "conflicting workload scopes")
            require(type(self.games) is int and self.games > 0, "invalid workload game count")
            require(type(self.seed) is int and 0 <= self.seed < 2**64, "invalid workload seed")

    def add(self, case):
        if self.games is None:
            return
        require(self.index < 3 * self.games, "extra workload game")
        count, game = 2 + self.index // self.games, self.index % self.games
        expected_seed = (self.seed + count * 1_000_000 + game) % 2**64
        require(type(case["seed"]) is int and case["seed"] == expected_seed
                and len(case["before"]["players"]) == count, "workload game schedule mismatch")
        require(case["policy"] == ("strong" if game % 2 == 0 else "random"),
                "workload policy schedule mismatch")
        before, after = case["before"], case["after"]
        if self.previous is None:
            require(before["turns"] == 0 and not before["terminal"], "workload game must start at turn zero")
        else:
            require(before == self.previous, "workload snapshot discontinuity")
        self.cases += 1
        require(self.cases <= 1000, "workload exceeds exporter turn cap")
        if after["terminal"] or case.get("status") == "no_legal_action" or self.cases == 1000:
            self.index += 1
            self.previous = None
            self.cases = 0
        else:
            self.previous = after

    def finish(self):
        if self.games is None:
            return {"checked": False, "reason": "boundary-history export has no full-game schedule"}
        require(self.previous is None and self.index == 3 * self.games,
                "incomplete workload game sequence")
        return {"checked": True, "games": self.index, "turn_cap": 1000,
                "scope": "Local snapshot continuity and declared exporter schedule only"}


def boundary_coverage(before, after, actions):
    """Classify one already-validated shared transition; preserve zero counts."""
    counts = {f"tier_{tier}_{event}": 0 for tier in range(1, 4)
              for event in ("final_draw", "empty_deck_purchase", "empty_deck_reserve")}
    counts.update({event: 0 for event in (
        "reserve_without_gold", "return_gold", "required_gold_payment",
        "free_purchase", "noble_after_take", "noble_after_reserve")})
    counts.update({f"reserved_purchase_{kind}_slot_{slot}": 0 for kind in ("public", "blind") for slot in range(3)})
    tag, slot = actions[0][:2]
    actor = before["current"]
    if tag in (1, 3):
        tier = slot // 4
        if before["remaining"][tier] == 1 and after["remaining"][tier] == 0:
            counts[f"tier_{tier + 1}_final_draw"] = 1
        if before["remaining"][tier] == 0:
            event = "empty_deck_reserve" if tag == 1 else "empty_deck_purchase"
            counts[f"tier_{tier + 1}_{event}"] = 1
    counts["reserve_without_gold"] = int(tag == 1 and before["bank"][5] == 0)
    counts["return_gold"] = int(any(a[0] == 6 and a[6] > 0 for a in actions))
    if tag == 4:
        kind = "public" if before["players"][actor]["reserved"][slot]["public"] else "blind"
        counts[f"reserved_purchase_{kind}_slot_{slot}"] = 1
    if tag in (3, 4):
        gold = before["players"][actor]["tokens"][5] - after["players"][actor]["tokens"][5]
        counts["required_gold_payment"] = int(gold > 0)
        payment = next(a[1:6] for a in actions if a[0] == 5)
        counts["free_purchase"] = int(not any(payment) and gold == 0)
    noble = before["players"][actor]["nobles"] != after["players"][actor]["nobles"]
    counts["noble_after_take"] = int(tag == 0 and noble)
    counts["noble_after_reserve"] = int(tag == 1 and noble)
    return counts


def validate_sampling(metadata, case):
    interval = metadata.get("choice_interval", 0)
    boundary_choices = metadata.get("boundary_choices", False)
    require(type(interval) is int and interval >= 0, "invalid choice interval")
    require(type(boundary_choices) is bool, "invalid boundary sampling flag")
    noble_acquisitions = metadata.get("noble_acquisition_choices", False)
    require(type(noble_acquisitions) is bool, "invalid noble acquisition sampling flag")
    require(not noble_acquisitions or boundary_choices, "noble acquisition sampling requires boundary sampling")
    before, after = case["before"], case["after"]
    require(type(metadata.get("winner_checks", False)) is bool, "invalid winner check flag")
    if metadata.get("winner_checks"):
        require("winner_mask" in before and "winner_mask" in after, "missing exported winner mask")
        if metadata.get("choice_successors"):
            require(all("winner_mask" in choice.get("after", {}) for choice in case.get("choices") or []),
                    "missing branch winner mask")
    boundary = boundary_choices and (
        after["terminal"] or any(a[0] == 7 for a in case["actions"])
        or (noble_acquisitions and before["nobles"] != after["nobles"])
        or (not before["final_round"] and after["final_round"]))
    required = boundary or (interval > 0 and before["turns"] % interval == 0)
    if "depletion_tier" in metadata:
        tier = metadata["depletion_tier"]
        require(type(tier) is int and 0 <= tier <= 2, "invalid depletion tier")
        required |= before["remaining"][tier] <= 1
    if "choice_interval" in metadata:
        required |= case.get("status") == "no_legal_action"
    require(not required or isinstance(case.get("choices"), list), "missing required choice sample")


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
        self.align_draw(rule, before, after)
        rule.current_agent_index = before["current"]
        return rule

    def align_draw(self, rule, before, after):
        state = rule.current_game_state
        # One turn draws at most one card. Align that exogenous draw; do not
        # claim RNG or hidden deck-order equivalence between implementations.
        for old, new in zip(before["market"], after["market"]):
            if old != new and new != 255:
                card = self.cards[new]
                deck = state.board.decks[card.deck_id]
                require(card in deck, "replacement card not in deck")
                deck.remove(card)
                deck.append(card)

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

    @staticmethod
    def validate_path(actions, noble_id):
        require(bool(actions), "empty compound action")
        require(all(isinstance(a, list) and len(a) == 7
                    and all(type(v) is int and 0 <= v <= 255 for v in a) for a in actions),
                "invalid action encoding")
        tags = [a[0] for a in actions]
        require(tags[0] in range(5), "invalid main action tag")
        expected = [tags[0]]
        if tags[0] in (3, 4):
            expected.append(5)
        elif 6 in tags:
            expected.append(6)
        if 7 in tags:
            expected.append(7)
        require(tags == expected, "invalid compound action phase order")
        payload_sizes = {0: 5, 1: 1, 2: 1, 3: 1, 4: 1, 5: 5, 6: 6, 7: 1}
        require(all(not any(a[payload_sizes[a[0]] + 1:]) for a in actions), "nonzero action padding")
        if tags[-1] == 7:
            require(actions[-1][1] == noble_id, "encoded noble choice disagrees with acquired noble")

    def candidate(self, before, actions, noble_id, rule):
        self.validate_path(actions, noble_id)
        tag, payload = actions[0][0], actions[0][1:]
        if tag == 2:
            return "blind_reservation"
        p = before["players"][before["current"]]
        noble = self.nobles[noble_id] if noble_id != 255 else None
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
            payment = next(a[1:6] for a in actions if a[0] == 5)
            cost = sum(max(card.cost.get(c, 0) - p["bonuses"][i], 0) for i, c in enumerate(COLORS[:5]))
            payment = payment + [cost - sum(payment)]
            paid = {c: n for c, n in zip(COLORS, payment) if n}
            if paid != rule.resources_sufficient(rule.current_game_state.agents[before["current"]], card.cost):
                return "optional_gold_payment"
            action.update(type="buy_available" if tag == 3 else "buy_reserve", card=card,
                          card_position=divmod(payload[0], 4) if tag == 3 else (3, payload[0]), returned_gems=paid)
        else:
            raise ValueError(f"unexpected main action {tag}")
        return action

    @staticmethod
    def signature(action):
        return (action["type"], action["card"].code if "card" in action else None,
                tuple(action.get("collected_gems", {}).get(c, 0) for c in COLORS),
                tuple(action.get("returned_gems", {}).get(c, 0) for c in COLORS),
                action["noble"][0] if action["noble"] else None)

    def check_noble_phase(self, action, path, legal):
        base = self.signature(action)[:-1]
        options = {self.signature(a)[-1] for a in legal if self.signature(a)[:-1] == base}
        require((len(options) > 1) == any(a[0] == 7 for a in path),
                "encoded noble phase disagrees with available noble choices")

    def compare_choices(self, case, check_successors=False):
        before = case["before"]
        rule = self.hydrate(before, before)
        local, reference = set(), set()
        legal = rule.getLegalActions(rule.current_game_state, before["current"])
        counts = collections.Counter()
        for choice in case["choices"]:
            if check_successors:
                require(isinstance(choice.get("after"), dict), "missing choice successor")
            action = self.candidate(before, choice["actions"], choice["noble"], rule)
            if check_successors:
                self.check_turn_bookkeeping(before, choice["after"], choice["actions"])
                self.check_reservation_bookkeeping(before, choice["after"], choice["actions"])
                self.check_token_bookkeeping(before, choice["after"], choice["actions"])
                self.check_blind_card_bookkeeping(before, choice["after"], choice["actions"])
                self.check_prestige_bookkeeping(before, choice["after"], choice["actions"])
                actor = before["current"]
                gained = (set(choice["after"]["players"][actor]["nobles"])
                          - set(before["players"][actor]["nobles"]))
                require(gained == (set() if choice["noble"] == 255 else {choice["noble"]}),
                        "choice noble disagrees with successor")
            if isinstance(action, str):
                counts["local_" + action] += 1
            else:
                self.check_noble_phase(action, choice["actions"], legal)
                key = self.signature(action)
                require(key not in local, "duplicate local compound action")
                local.add(key)
                if check_successors:
                    after = choice["after"]
                    result = self.compare({"before": before, "after": after, "actions": choice["actions"]}, counts)
                    require(result == "matched", f"shared successor was excluded: {result}")
                    counts.update({"boundary_" + k: v for k, v in boundary_coverage(before, after, choice["actions"]).items()})
                    counts["shared_successors"] += 1
                    counts[f"successors_players_{len(before['players'])}"] += 1
                    counts["successors_terminal"] += int(after["terminal"])
                    counts["successors_noble"] += int(bool(gained))
                    explicit_noble = any(a[0] == 7 for a in choice["actions"])
                    counts["successors_explicit_noble_choice"] += int(explicit_noble)
                    if explicit_noble:
                        counts[f"successors_explicit_noble_choice_players_{len(before['players'])}"] += 1
        for action in legal:
            if action["type"] == "pass":
                counts["reference_pass"] += 1
                continue
            if action["type"] == "collect_diff" and sum(action["collected_gems"].values()) != min(3, sum(n > 0 for n in before["bank"][:5])):
                counts["reference_reduced_take"] += 1
                continue
            key = self.signature(action)
            require(key not in reference, "duplicate reference compound action")
            reference.add(key)
        require(local == reference, f"action-set mismatch: local only {local - reference}, reference only {reference - local}")
        counts["positions"] += 1
        counts["shared_choices"] += len(local)
        return counts

    @staticmethod
    def check_local_winner(snapshot):
        scores = [p["score"] for p in snapshot["players"]]
        final_round = max(scores) >= 15
        require(snapshot["final_round"] == final_round, "final-round flag disagrees with scores")
        require(snapshot["terminal"] == (final_round and snapshot["current"] == 0),
                "terminal flag disagrees with round boundary")
        if "winner_mask" not in snapshot:
            return
        if not snapshot["terminal"]:
            require(snapshot["winner_mask"] is None, "unfinished state has a winner")
            return
        leaders = [i for i, score in enumerate(scores) if score == max(scores)]
        fewest = min(len(snapshot["players"][i]["owned"]) for i in leaders)
        expected = sum(1 << i for i in leaders if len(snapshot["players"][i]["owned"]) == fewest)
        require(type(snapshot["winner_mask"]) is int and snapshot["winner_mask"] == expected,
                "winner mask disagrees with leader-only fewest-card rule")

    def compare_winner(self, rule, snapshot, counts):
        if "winner_mask" not in snapshot:
            return
        if not snapshot["terminal"]:
            if counts is not None:
                counts["unfinished_without_winner"] += 1
            return
        state = rule.current_game_state
        scores = [rule.calScore(state, i) for i in range(len(state.agents))]
        reference_mask = sum(1 << i for i, score in enumerate(scores) if score == max(scores))
        local_mask = snapshot["winner_mask"]
        if reference_mask == local_mask:
            result = "winner_matches"
            if counts is not None and local_mask.bit_count() > 1:
                counts["shared_winner_matches"] += 1
        else:
            prestige = [p["score"] for p in snapshot["players"]]
            card_counts = [len(p["owned"]) for p in snapshot["players"]]
            leaders = [i for i, score in enumerate(prestige) if score == max(prestige)]
            leader_mask = sum(1 << i for i in leaders)
            require(min(card_counts) < min(card_counts[i] for i in leaders)
                    and local_mask != leader_mask and reference_mask == leader_mask,
                    "unclassified reference winner mismatch")
            result = "reference_global_fewest_card_defect"
        if counts is not None:
            counts[result] += 1
            counts[f"{result}_players_{len(state.agents)}"] += 1

    @staticmethod
    def check_reservation_bookkeeping(before, after, actions):
        # The reference stores identities but has no visibility flags. Check
        # local preservation separately; this is not observation parity.
        require(len(before["players"]) == len(after["players"]), "player count changed")
        for snapshot in (before, after):
            require(all(type(r.get("public")) is bool for p in snapshot["players"] for r in p["reserved"]),
                    "invalid reservation visibility flag")
        actor = before["current"]
        tag, slot = actions[0][:2]
        for i, (old, new) in enumerate(zip(before["players"], after["players"])):
            expected = list(old["reserved"])
            actual = new["reserved"]
            if i == actor:
                if tag == 1:
                    expected.append({"card": before["market"][slot], "public": True})
                elif tag == 2:
                    require(len(actual) == len(expected) + 1 and actual[-1]["public"] is False,
                            "invalid blind reservation append")
                    expected.append(actual[-1])
                elif tag == 4:
                    require(slot < len(expected), "invalid reserved purchase slot")
                    expected.pop(slot)
            require(actual == expected, "reservation identity, visibility, or order changed")

    def check_blind_card_bookkeeping(self, before, after, actions):
        if actions[0][0] != 2:
            return
        tier = actions[0][1]
        require(tier < 3, 'invalid blind reservation tier')
        actor = before['current']
        card = after['players'][actor]['reserved'][-1]['card']
        require(type(card) is int and 0 <= card < len(self.cards)
                and self.cards[card].deck_id == tier, 'blind reservation card tier mismatch')
        require(before['market'] == after['market'], 'blind reservation changed market')
        expected = list(before['remaining'])
        require(len(expected) == 3 and expected[tier] > 0, 'blind reservation from empty deck')
        expected[tier] -= 1
        require(after['remaining'] == expected, 'blind reservation deck count mismatch')
        for old, new in zip(before['players'], after['players']):
            require(old['owned'] == new['owned'] and old['bonuses'] == new['bonuses'],
                    'blind reservation changed purchased cards or bonuses')
        for snapshot in (before, after):
            require(isinstance(snapshot['remaining'], list) and len(snapshot['remaining']) == 3
                    and all(type(n) is int and 0 <= n <= 40 for n in snapshot['remaining']),
                    'invalid blind reservation deck counts')
            used = [c for c in snapshot['market'] if c != 255]
            for player in snapshot['players']:
                used.extend(player['owned'])
                used.extend(r['card'] for r in player['reserved'])
            require(all(type(c) is int and 0 <= c < len(self.cards) for c in used)
                    and len(used) == len(set(used)), 'blind reservation card partition duplicate or invalid ID')
            remaining = [sum(c.deck_id == t for c in self.cards)
                         - sum(self.cards[c].deck_id == t for c in used) for t in range(3)]
            require(snapshot['remaining'] == remaining, 'blind reservation card partition count mismatch')
        # The partition and unchanged prior reservations imply that the new card
        # was in the requested deck. Its order in that deck is not observable here.

    def check_token_bookkeeping(self, before, after, actions):
        # Local contract for all branches, including reference exclusions.
        # This is not an independent reference transition comparison.
        for snapshot in (before, after):
            vectors = [snapshot['bank']] + [p['tokens'] for p in snapshot['players']]
            require(all(isinstance(v, list) and len(v) == 6
                        and all(type(n) is int and 0 <= n <= 255 for n in v) for v in vectors),
                    'invalid token vector')
        actor = before['current']
        bank = list(before['bank'])
        hands = [list(p['tokens']) for p in before['players']]
        tag, slot = actions[0][:2]
        transfer = [0]*6  # Positive amounts move from bank to actor.
        if tag == 0:
            transfer = actions[0][1:6] + [0]
        elif tag in (1, 2):
            transfer[5] = int(bank[5] > 0)
        elif tag in (3, 4):
            player = before['players'][actor]
            card_id = before['market'][slot] if tag == 3 else player['reserved'][slot]['card']
            card = self.cards[card_id]
            cost = [max(card.cost.get(c, 0) - player['bonuses'][i], 0)
                    for i, c in enumerate(COLORS[:5])]
            colored = actions[1][1:6]
            require(all(paid <= due for paid, due in zip(colored, cost)), 'token overpayment')
            transfer = [-paid for paid in colored] + [-(sum(cost) - sum(colored))]
        for c, amount in enumerate(transfer):
            bank[c] -= amount
            hands[actor][c] += amount
        require(min(bank + hands[actor]) >= 0, 'token overdraft')
        returns = [a[1:] for a in actions if a[0] == 6]
        excess = max(sum(hands[actor]) - 10, 0)
        require(bool(returns) == (excess > 0), 'token return phase disagrees with excess')
        if returns:
            returned = returns[0]
            require(sum(returned) == excess and all(r <= n for r, n in zip(returned, hands[actor])),
                    'invalid token return')
            for c, amount in enumerate(returned):
                bank[c] += amount
                hands[actor][c] -= amount
        require(bank == after['bank'] and hands == [p['tokens'] for p in after['players']],
                'token successor mismatch')

    def check_prestige_bookkeeping(self, before, after, actions):
        for snapshot in (before, after):
            noble_ids = list(snapshot['nobles'])
            for player in snapshot['players']:
                owned = player['owned']
                require(all(type(c) is int and 0 <= c < len(self.cards) for c in owned)
                        and len(owned) == len(set(owned)), 'invalid prestige card ownership')
                nobles = player['nobles']
                noble_ids.extend(nobles)
                bonuses = [sum(self.cards[c].colour == color for c in owned) for color in COLORS[:5]]
                require(player['bonuses'] == bonuses, 'prestige bonuses disagree with owned cards')
                score = sum(self.cards[c].points for c in owned) + 3 * len(nobles)
                require(type(player['score']) is int and player['score'] == score,
                        'prestige score disagrees with owned cards and nobles')
            require(all(type(n) is int and 0 <= n < len(self.nobles) for n in noble_ids)
                    and len(noble_ids) == len(set(noble_ids)) == len(snapshot['players']) + 1,
                    'invalid noble partition')
        actor = before['current']
        tag, slot = actions[0][:2]
        for seat, (old, new) in enumerate(zip(before['players'], after['players'])):
            owned = set(old['owned'])
            if seat == actor and tag in (3, 4):
                owned.add(before['market'][slot] if tag == 3 else old['reserved'][slot]['card'])
            require(set(new['owned']) == owned, 'prestige ownership transition mismatch')
            require(set(old['nobles']) <= set(new['nobles']), 'lost claimed noble')
            if seat != actor:
                require(old['nobles'] == new['nobles'], 'opponent noble changed')
        player = after['players'][actor]
        gained = set(player['nobles']) - set(before['players'][actor]['nobles'])
        eligible = {n for n in before['nobles']
                    if all(player['bonuses'][i] >= self.nobles[n][1].get(c, 0)
                           for i, c in enumerate(COLORS[:5]))}
        require(gained <= eligible and len(gained) == int(bool(eligible)),
                'mandatory noble acquisition mismatch')
        require(set(after['nobles']) == set(before['nobles']) - gained, 'available noble transition mismatch')
        choices = [a[1] for a in actions if a[0] == 7]
        require(bool(choices) == (len(eligible) > 1) and (not choices or set(choices) == gained),
                'encoded noble phase disagrees with eligible choices')

    def check_turn_bookkeeping(self, before, after, actions):
        count = len(before['players'])
        require(2 <= count <= 4 and len(after['players']) == count, 'invalid turn player count')
        for snapshot in (before, after):
            require(type(snapshot['turns']) is int and 0 <= snapshot['turns'] < 2**32,
                    'invalid turn counter')
            require(type(snapshot['current']) is int and 0 <= snapshot['current'] < count
                    and snapshot['turns'] % count == snapshot['current'], 'turn seat mismatch')
            require(type(snapshot['final_round']) is bool and type(snapshot['terminal']) is bool,
                    'invalid turn flags')
            self.check_local_winner(snapshot)
        if actions:
            require(not before['terminal'], 'action after terminal turn')
            require(after['turns'] == before['turns'] + 1, 'complete turn did not advance once')
            require(after['current'] == (before['current'] + 1) % count, 'incorrect next turn player')
            expected_final = before['final_round'] or after['players'][before['current']]['score'] >= 15
            require(after['final_round'] == expected_final, 'invalid final-round turn transition')

    def compare(self, case, winner_counts=None):
        before, after, actions = case["before"], case["after"], case["actions"]
        self.check_turn_bookkeeping(before, after, actions)
        if not actions:
            require(case.get("status") == "no_legal_action" and before == after and not before["terminal"], "invalid blocked-state record")
            if winner_counts is not None and "winner_mask" in after:
                winner_counts["blocked_without_winner"] += 1
            return "no_legal_action"
        actor = before["current"]
        gained = set(after["players"][actor]["nobles"]) - set(before["players"][actor]["nobles"])
        require(len(gained) <= 1, "multiple noble acquisitions")
        noble_id = next(iter(gained)) if gained else 255
        self.validate_path(actions, noble_id)
        self.check_reservation_bookkeeping(before, after, actions)
        self.check_token_bookkeeping(before, after, actions)
        self.check_blind_card_bookkeeping(before, after, actions)
        self.check_prestige_bookkeeping(before, after, actions)
        if actions[0][0] == 2:
            return "blind_reservation"
        rule = self.hydrate(before, after)
        action = self.candidate(before, actions, next(iter(gained)) if gained else 255, rule)
        if isinstance(action, str):
            return action
        legal = rule.getLegalActions(rule.current_game_state, before["current"])
        require(action in legal, f"reference rejects shared action: {action}")
        self.check_noble_phase(action, actions, legal)
        rule.update(action)
        actual = self.normalized(rule)
        expected = {key: after[key] for key in actual if key != "players"}
        expected["players"] = [{**{k: v for k, v in p.items() if k != "reserved"},
                                "reserved": [r["card"] for r in p["reserved"]]} for p in after["players"]]
        require(actual == expected, f"successor mismatch: expected {expected}, got {actual}")
        self.compare_winner(rule, after, winner_counts)
        return "matched"


class SharedChains:
    """Keep external successors across shared turns; reset only at explicit gaps."""

    def __init__(self, comparison):
        self.comparison = comparison
        self.rule = None
        self.previous = None
        self.identity = None
        self.length = 0
        self.start_turn = None
        self.lengths = collections.Counter()
        self.breaks = collections.Counter()
        self.complete_games = []

    def close(self):
        if self.length:
            self.lengths[self.length] += 1
        self.rule = None
        self.length = 0

    def add(self, case, isolated_result):
        before, after = case["before"], case["after"]
        identity = (len(before["players"]), case["seed"])
        if identity != self.identity:
            self.close()
            self.previous = None
            self.identity = identity
        if self.previous is not None:
            require(before == self.previous, "chain input snapshot discontinuity")
        self.previous = after
        if isolated_result != "matched":
            self.close()
            self.breaks[isolated_result] += 1
            return
        comparison = self.comparison
        if self.rule is None:
            self.rule = comparison.hydrate(before, before)
            self.start_turn = before["turns"]
        actual_before = comparison.normalized(self.rule)
        require(actual_before == self.expected(before, actual_before), "retained reference state differs before turn")
        comparison.align_draw(self.rule, before, after)
        actor = before["current"]
        gained = set(after["players"][actor]["nobles"]) - set(before["players"][actor]["nobles"])
        action = comparison.candidate(before, case["actions"], next(iter(gained)) if gained else 255, self.rule)
        require(not isinstance(action, str), "retained reference changed shared action classification")
        legal = self.rule.getLegalActions(self.rule.current_game_state, actor)
        require(action in legal, "retained reference rejects shared action")
        comparison.check_noble_phase(action, case["actions"], legal)
        self.rule.update(action)
        actual_after = comparison.normalized(self.rule)
        require(actual_after == self.expected(after, actual_after), "retained reference successor mismatch")
        comparison.compare_winner(self.rule, after, None)
        self.length += 1
        if after["terminal"]:
            if self.start_turn == 0:
                self.complete_games.append({"players": identity[0], "seed": identity[1],
                                            "turns": self.length, "winner_mask": after.get("winner_mask")})
            self.close()

    @staticmethod
    def expected(snapshot, normalized):
        result = {key: snapshot[key] for key in normalized if key != "players"}
        result["players"] = [{**{k: v for k, v in p.items() if k != "reserved"},
                              "reserved": [r["card"] for r in p["reserved"]]} for p in snapshot["players"]]
        return result

    def finish(self):
        self.close()
        return {"segments": sum(self.lengths.values()),
                "turns": sum(k * v for k, v in self.lengths.items()),
                "max_segment_turns": max(self.lengths, default=0),
                "segment_length_histogram": dict(sorted(self.lengths.items())),
                "breaks": dict(self.breaks), "complete_games_without_reset": len(self.complete_games),
                "complete_game_records": self.complete_games,
                "scope": "Retained external state across shared turns; only replacement draws aligned. State reset after each explicit rule exclusion. Not RNG or hidden-information parity."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=pathlib.Path, required=True)
    parser.add_argument("--cases", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--chains", action="store_true", help="also retain reference state across consecutive shared turns")
    args = parser.parse_args()
    comparison = Comparison(args.reference.resolve())
    chains = SharedChains(comparison) if args.chains else None
    counts = collections.Counter()
    categories = collections.Counter()
    choice_counts = collections.Counter()
    winner_counts = collections.Counter()
    digest = hashlib.sha256()
    with args.cases.open("rb") as stream:
        first = next(stream)
        digest.update(first)
        metadata = json.loads(first)
        require(metadata["format"] in (1, 2), "unsupported export format")
        check_successors = metadata["format"] == 2
        if check_successors:
            require(metadata.get("choice_successors") is True, "missing successor export flag")
        sequence = WorkloadSequence(metadata)
        for line_number, line in enumerate(stream, 2):
            digest.update(line)
            case = json.loads(line)
            try:
                sequence.add(case)
                validate_sampling(metadata, case)
                result = comparison.compare(case, winner_counts)
                if chains is not None:
                    chains.add(case, result)
                if case.get("choices") is not None:
                    choice_counts.update(comparison.compare_choices(case, check_successors))
            except (ValueError, KeyError, IndexError) as exc:
                raise ValueError(f"case line {line_number}, seed {case['seed']}, turn {case['before']['turns']}: {exc}") from exc
            counts[result] += 1
            if result == "matched":
                categories.update({"boundary_" + k: v for k, v in boundary_coverage(case["before"], case["after"], case["actions"]).items()})
                categories[f"players_{len(case['before']['players'])}"] += 1
                categories[f"action_{case['actions'][0][0]}"] += 1
                categories["terminal"] += int(case["after"]["terminal"])
                categories["noble"] += int(case["before"]["nobles"] != case["after"]["nobles"])
    workload_sequence = sequence.finish()
    require(counts["matched"] > 0, "no shared transitions were checked")
    report = {"reference": "https://github.com/roeey777/Splendor-AI", "commit": REFERENCE_COMMIT,
              "license": "MIT", "license_sha256": comparison.license_hash, "export": metadata,
              "cases_sha256": digest.hexdigest(),
              "harness_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              "exporter_sha256": hashlib.sha256((ROOT / "crates/splendor-arena/examples/parity_export.rs").read_bytes()).hexdigest(),
              "cards_matched": 90, "nobles_matched": 10,
              "workload_sequence": workload_sequence,
              "cases": dict(counts), "matched_coverage": dict(categories), "action_sets": dict(choice_counts),
              "selected_winners": dict(winner_counts),
              "scope": "Shared complete-turn transitions and sampled shared action sets, with branch successors when exported; aligned exogenous draws. Winner masks checked when exported, with explicit reference tiebreak defects. Not full rules, RNG, observation, or rank parity."}
    if chains is not None:
        report["shared_chains"] = chains.finish()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
