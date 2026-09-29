#!/usr/bin/env python3
"""Retained-state stdlib reference adapter; no upstream rules or logs patched."""
import argparse
import collections
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'benchmarks'))
from check_reference import Comparison, COLORS, REFERENCE_COMMIT
from make_corpus import Rng


def setup(comparison, case):
    rule = comparison.Rule(2)
    board = rule.current_game_state.board
    for tier, row in enumerate(case['decks']):
        assert len(row) == (40, 30, 20)[tier] and len(set(row)) == len(row)
        assert all(comparison.cards[i].deck_id == tier for i in row)
        board.dealt[tier] = [comparison.cards[i] for i in row[:4]]
        board.decks[tier] = [comparison.cards[i] for i in reversed(row[4:])]
    assert len(case['nobles']) == 3 and len(set(case['nobles'])) == 3
    board.nobles = [comparison.nobles[i] for i in case['nobles']]
    comparison.check_reference_partition(rule)
    return rule


def snapshot(comparison, rule):
    state = rule.current_game_state
    return {'bank': [state.board.gems[c] for c in COLORS],
            'players': [{'tokens': [p.gems[c] for c in COLORS],
                         'bonuses': [len(p.cards[c]) for c in COLORS[:5]],
                         'score': p.score,
                         'reserved': sorted(comparison.card_ids[x.code] for x in p.cards['yellow'])}
                        for p in state.agents],
            'market': sorted(comparison.card_ids[x.code] for row in state.board.dealt for x in row if x),
            'remaining': [len(x) for x in state.board.decks],
            'nobles': sorted(comparison.noble_ids[x[0]] for x in state.board.nobles),
            'current': rule.current_agent_index, 'turns': rule.action_counter,
            'terminal': rule.gameEnds()}


def projected(comparison, rule, native):
    player = rule.current_game_state.agents[rule.current_agent_index]
    total = sum(player.gems.values())
    choices = {}
    for action in native:
        kind = action['type']
        if kind in ('buy_available', 'buy_reserve'):
            key = comparison.card_ids[action['card'].code] + (100 if kind == 'buy_reserve' else 0)
        elif kind == 'reserve':
            if action['returned_gems'] or total + sum(action['collected_gems'].values()) > 10:
                continue
            key = 2000 + comparison.card_ids[action['card'].code]
        elif kind in ('collect_diff', 'collect_same'):
            q = [action['collected_gems'].get(c, 0) for c in COLORS[:5]]
            if action['returned_gems'] or total > 7:
                continue
            if not (sum(q) == 3 and max(q) == 1 or sum(q) == 2 and max(q) == 2):
                continue
            key = 1000 + sum(n * 3 ** i for i, n in enumerate(q))
        else:
            continue
        # Multiple compound noble choices share one projected main action. The
        # selected multi-eligible purchase stops before any native apply.
        choices.setdefault(key, action)
    # Native has a seven-bonus purchase cap. Preserve the common action list,
    # but label that action unsupported rather than changing the distribution.
    for reserved, cards in [(False, rule.current_game_state.board.dealt_list()),
                            (True, player.cards['yellow'])]:
        for card in cards:
            if len(player.cards[card.colour]) == 7 and isinstance(rule.resources_sufficient(player, card.cost), dict):
                key = comparison.card_ids[card.code] + (100 if reserved else 0)
                choices.setdefault(key, {'type': 'unsupported_bonus_cap', 'card': card})
    return sorted(choices.items())


def play(comparison, rule, case, policy, trace, max_turns):
    start = time.perf_counter()
    rng = Rng(case['policy_seed'])
    history = [snapshot(comparison, rule)] if trace else []
    action_keys, legal_keys = [], []
    status = 'decision_limit'
    for _ in range(max_turns):
        if rule.gameEnds():
            status = 'complete'
            break
        actor = rule.current_agent_index
        native = rule.getLegalActions(rule.current_game_state, actor)
        choices = projected(comparison, rule, native)
        if trace:
            legal_keys.append([x[0] for x in choices])
        if not choices:
            state = rule.current_game_state
            p = state.agents[actor]
            # Within this profile, colored-empty plus three reservations and
            # no affordable buy is exactly the canonical no-action state.
            status = 'no_legal_action' if len(p.cards['yellow']) == 3 and not any(state.board.gems[c] for c in COLORS[:5]) else 'profile_blocked'
            break
        if policy == 'random':
            index = rng.index(len(choices))
        elif choices[0][0] < 1000:
            index = 0
        else:
            takes = [(sum(action['collected_gems'].get(c, 0) * (8 - rule.current_game_state.agents[actor].gems[c])
                          for c in COLORS[:5]), -i, i)
                     for i, (key, action) in enumerate(choices) if 1000 <= key < 2000]
            index = max(takes)[2] if takes else 0
        key, action = choices[index]
        p = rule.current_game_state.agents[actor]
        if key < 1000:
            card = action['card']
            eligible = sum(all(len(p.cards[c]) + int(card.colour == c) >= cost
                               for c, cost in noble[1].items())
                           for noble in rule.current_game_state.board.nobles)
            if eligible >= 2:
                status = 'unsupported_noble_choice'
                break
        if action['type'] == 'unsupported_bonus_cap':
            status = 'unsupported_reference_bonus_cap'
            break
        # update assumes valid input. Explicit membership in the native legal
        # list is the validation contract; it does not repeat enumeration.
        assert action in native, 'selected compound action is not native legal'
        rule.update(action)
        if trace:
            action_keys.append(key)
            history.append(snapshot(comparison, rule))
    if rule.gameEnds():
        status = 'complete'
    latency = time.perf_counter() - start
    return {'seed': case['seed'], 'status': status, 'turns': rule.action_counter,
            'decisions': rule.action_counter, 'latency_seconds': latency,
            'final_state': None, 'trace': history, 'action_keys': action_keys,
            'legal_keys': legal_keys}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT / 'local/benchmarks/external/python_roeey')
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--policy', choices=['random', 'fixed'], default='random')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--max-turns', type=int, default=20000)
    args = parser.parse_args()
    if args.threads != 1 or args.repetitions < 1:
        parser.error('serial only; repetitions must be positive')
    startup = time.perf_counter()
    comparison = Comparison(args.root)
    corpus = json.loads(args.corpus.read_text())
    assert corpus['profile'] == 'seal256-intersection-v1'
    startup_seconds = time.perf_counter() - startup
    samples = []
    for _ in range(args.repetitions):
        setup_start = time.perf_counter()
        rules = [setup(comparison, c) for c in corpus['cases']]
        setup_seconds = time.perf_counter() - setup_start
        start = time.perf_counter()
        records = [play(comparison, rule, case, args.policy, args.trace, args.max_turns)
                   for rule, case in zip(rules, corpus['cases'])]
        seconds = time.perf_counter() - start
        for record, rule in zip(records, rules):
            record['final_state'] = snapshot(comparison, rule)
            comparison.check_reference_partition(rule)
        statuses = dict(collections.Counter(r['status'] for r in records))
        samples.append({'seconds': seconds, 'setup_seconds': setup_seconds, 'count': len(records),
                        'completed': statuses.get('complete', 0), 'statuses': statuses,
                        'turns': sum(r['turns'] for r in records),
                        'decisions': sum(r['decisions'] for r in records), 'records': records})
    result = {'engine': 'roeey777/Splendor-AI', 'revision': REFERENCE_COMMIT,
              'profile': corpus['profile'], 'policy': args.policy, 'threads': 1,
              'rank_eligible': False, 'whole_game_comparable': False,
              'python': platform.python_version(), 'startup_seconds': startup_seconds,
              'license_sha256': comparison.license_hash, 'samples': samples,
              'timing_boundary': 'Prepared states; native compound legal generation, common projection/policy, native legal membership validation, update, per-game clock and typed records; setup, final snapshots and serialization excluded. Native action_reward history bookkeeping remains enabled.',
              'limitations': ['Serial only.', 'No whole-game rank: the seven-bonus cap changes the shared action domain, and mandatory native history bookkeeping violates the logging-excluded timing contract.',
                              'Seven-bonus selected purchase reports unsupported_reference_bonus_cap.',
                              'Mandatory upstream in-memory action history remains enabled and is copied during legal generation; no logging-disable interface exists.',
                              'No UI, network, training, model, database or external logging imports.']}
    print(json.dumps(result, separators=(',', ':')))


if __name__ == '__main__':
    main()
