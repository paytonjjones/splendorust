"""Summarize the four fixed browser games; do not select from partial results."""
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
plan = json.loads((ROOT / 'PLAN.json').read_text())
rows = [json.loads(line) for line in (ROOT / 'games.jsonl').read_text().splitlines()]
games = [row['record'] for row in rows if row.get('type') == 'game']
assert len(games) == plan['games']
assert {(g['seed'], g['batchSeat']) for g in games} == {(s, seat) for s in plan['seeds'] for seat in (0, 1)}
credits = {}
wins = ties = losses = unknown = 0
replays = []
for g in games:
    result = g['result']
    if g['stopped'] or not result or result['status'] != 'finished':
        unknown += 1
        credits[(g['seed'], g['batchSeat'])] = None
    elif result['winnerMask'] == 3:
        ties += 1
        credits[(g['seed'], g['batchSeat'])] = 0.5
    elif result['winnerMask'] & (1 << g['batchSeat']):
        wins += 1
        credits[(g['seed'], g['batchSeat'])] = 1
    else:
        losses += 1
        credits[(g['seed'], g['batchSeat'])] = 0
    replays.append(g['replay'])
(ROOT / 'replays.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in replays))
turns = [t for g in games for t in g['turns']]
assert max(t['ms'] for t in turns) < 5100, 'Turn deadline exceeded'
cost = {}
for batch in (1, 8):
    active = [t for t in turns if t['batch'] == batch and t['simulations'] > 0]
    seconds = sum(t['ms'] for t in active) / 1000
    cost[str(batch)] = dict(main_searches=len(active), mean_simulations=statistics.mean(t['simulations'] for t in active),
        median_search_ms=statistics.median(t['ms'] for t in active),
        simulations_per_second=sum(t['simulations'] for t in active)/seconds,
        inferences_per_second=sum(t['inferences'] for t in active)/seconds,
        max_turn_ms=max(t['ms'] for t in turns if t['batch'] == batch))
point = (wins + ties * .5) / len(games)
low_point = point
high_point = point + unknown / len(games)
# Two independent setup clusters, including both seats and unknown endpoints.
radius = math.sqrt(math.log(40) / (2 * len(plan['seeds'])))
summary = dict(games=len(games), wins=wins, ties=ties, losses=losses, unknown=unknown,
    credit_bounds_unknowns=[low_point, high_point],
    conservative_cluster_ci95=[max(0, low_point-radius), min(1, high_point+radius)],
    ci_method='Conservative two-sided Hoeffding over two independent setup clusters. Too small to establish non-inferiority.',
    cost=cost, game_seconds=[g['elapsedMs']/1000 for g in games],
    game_records_sha256=hashlib.sha256((ROOT/'games.jsonl').read_bytes()).hexdigest(),
    scope='Chrome WebGPU, canonical rules, four fixed games, same weights and5s whole-turn limit. Exploratory only; no champion promotion.')
(ROOT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
