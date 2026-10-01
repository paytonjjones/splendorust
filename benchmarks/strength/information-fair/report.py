#!/usr/bin/env python3
"""Report fixed information contrasts after all schedules and audits finish."""
import json
from pathlib import Path
from boundary import ARMS, sha

BASE=Path(__file__).resolve().parent
LABEL={'control':'Control','blind-alpha':'Blind AlphaZero','privileged-sr':'Privileged SplendoRust'}

def pct(x): return f'{100*x:.3f}%'
def interval(bounds):
    if bounds is None: return 'Undefined (no positive control gap)'
    return pct(bounds[0]) if bounds[0]==bounds[1] else f'{pct(bounds[0])} to {pct(bounds[1])}'
def pp(bounds):
    if bounds[0]==bounds[1]: return f'{100*bounds[0]:+.3f}'
    return f'{100*bounds[0]:+.3f} to {100*bounds[1]:+.3f}'

def main():
    screen=json.loads((BASE/'screen/summary.json').read_text())
    confirm=json.loads((BASE/'confirmation/summary.json').read_text())
    freeze=json.loads((BASE/'freeze.json').read_text())
    audit=json.loads((BASE/'final-audit.json').read_text());assert audit['status']=='passed'
    control=confirm['arms']['control']['credit_bounds'][0]
    blind=confirm['contrasts']['blind-alpha']
    privileged=confirm['contrasts']['privileged-sr']
    lines=['# AlphaZero information fairness','',
        'Status: complete. All six schedules have passed full native replay and the final hash audit.', '',
        f"Control SplendoRust win credit is {pct(control)}. Blind AlphaZero changes that credit by {pp(blind['delta_credit_bounds'])} percentage points; privileged SplendoRust changes it by {pp(privileged['delta_credit_bounds'])} percentage points. The separate estimates of the control gap removed are {interval(blind['control_gap_reduced_fraction_bounds'])} and {interval(privileged['control_gap_reduced_fraction_bounds'])}. The paired uncertainty intervals are below. These two estimates must not be added.", '',
        'The experiment uses the current E81/Gumbel128 endpoint from E92. It changes the information supplied to one agent at a time. The native referee, game rules, models, weights and search budgets stay fixed. The existing canonical and native benchmarks remain unchanged.', '',
        '| Arm | SplendoRust input | AlphaZero input |','|---|---|---|',
        '| Control | Public history and own private cards | True unordered card partition |',
        '| Blind AlphaZero | Same as control | Public-consistent sampled partition |',
        '| Privileged SplendoRust | True unordered card partition | Same as control |','',
        'No arm supplies future deck order. Blind AlphaZero receives a board built only from public information and its own private reservations. Unknown opponent reservations and tier decks are sampled together, without replacement. Exact true remaining-deck membership cannot reveal a blind card because that membership is never supplied. Known public reservations and all public state remain available.', '',
        'Privileged SplendoRust receives exact opponent blind IDs and exact unordered tier membership. Its root worlds and neural leaves use the exact simulated partition. It uses the same search kernel and frozen model as the control. This path requires an explicit benchmark feature and a separate worker.', '',
        'The blind arm keeps the upstream MCTS unchanged. It supplies one public-consistent root sample per real decision and retains the three upstream chance universes. This tests an information input change. It does not introduce a new belief-search algorithm or establish the best possible use of public information.', '',
        '## Frozen protocol','',
        f"Frozen implementation revision: `{freeze['revision']}`. Full settings and file hashes are in [freeze.json](freeze.json). The hypothesis and seed plan preceded outcome runs in [PREREGISTRATION.md](PREREGISTRATION.md).", '',
        '| Item | Fixed value |','|---|---|',
        '| SplendoRust model | E81, `research/e81/model/model.bin` |',
        f"| SplendoRust model SHA256 | `{freeze['files']['research/e81/model/model.bin']}` |",
        '| SplendoRust search | Gumbel128, depth16, worlds3, 16 root candidates, c_visit50, c_scale0.1, noise0 |',
        '| SplendoRust PUCT terms | cpuct0.4, FPU reduction0.02965, uniform prior0 |',
        '| AlphaZero source | `lyquentxy/splendor`, `32a27ac1f85d5de2766cc5f60c2bf04e557f7836` |',
        f"| AlphaZero checkpoint SHA256 | `{freeze['upstream_files']['splendor/pretrained_2players.pt']}` |",
        '| AlphaZero search | 800 simulations, cpuct0.8, FPU0.0593, three universes, full search, no forced playouts, normal memory cleanup |',
        '| AlphaZero selection | Upstream pit argmax; temperature0.5 for first six total turns, then0 |',
        '| Screen | 2,000 games per arm, master4900000000, eight workers |',
        '| Confirmation | 20,000 games per arm, master4910000000, eight workers |','',
        'Every setup has both seat rotations. All three arms share setup, policy and referee chance streams. A separate information stream selects blind samples. Confirmation uses fresh blocks and does not select any setting. Win credit is one for a sole winner and one-half for a shared winner. Independent setup blocks, with both rotations and all three arms together, are the statistical sampling unit.', '',
        '## Confirmation','',
        '| Arm | Complete / requested | SR win credit | Paired bootstrap 95% | Hoeffding 95% |',
        '|---|---:|---:|---|---|']
    for arm in ARMS:
        r=confirm['arms'][arm]
        lines.append(f"| {LABEL[arm]} | {r['statuses'].get('complete',0):,} / {r['games']:,} | {interval(r['credit_bounds'])} | {interval(r['paired_bootstrap95_missing_envelope'])} | {interval(r['hoeffding95'])} |")
    lines+=['','| Independent intervention | SR credit change, percentage points | Paired bootstrap 95%, pp | Simultaneous Hoeffding 95%, pp | Fraction of control gap removed | Fraction bootstrap 95% |', '|---|---:|---|---|---:|---|']
    for arm in ARMS[1:]:
        r=confirm['contrasts'][arm]
        fraction=r['control_gap_reduced_fraction_bootstrap95']
        fraction_text=interval(fraction) if fraction else 'Not identified'
        lines.append(f"| {LABEL[arm]} | {pp(r['delta_credit_bounds'])} | {pp(r['paired_bootstrap95'])} | {pp(r['simultaneous_hoeffding95'])} | {interval(r['control_gap_reduced_fraction_bounds']) if r['control_gap_reduced_fraction_bounds'] else 'Not identified'} | {fraction_text} |")
    control=confirm['arms']['control']['credit_bounds']
    lines+=['',f"The control head-to-head gap, AlphaZero credit minus SplendoRust credit, is {interval([1-2*control[1],1-2*control[0]])}. A one-point increase in SR credit reduces that gap by two points. The reported fraction is the intervention's SR credit increase divided by the control shortfall from 50%.", '',
        'The two interventions estimate different counterfactuals. Their effects and gap fractions must not be added. Results apply to this native ruleset, these frozen models and these fixed budgets. They do not establish a canonical Splendor rank or an equal-compute rank.', '',
        'Bootstrap intervals use 20,000 resamples of whole matched setup blocks. The conservative intervals use Hoeffding bounds under the independent-block assumption. The two contrast bounds use a union bound for simultaneous 95% coverage. Bonferroni-adjusted paired bootstrap 97.5% intervals are also saved in the summary. Missing outcomes retain [0,1] credit bounds. No missing game is assigned a win.', '',
        '## Separate screen','', '| Arm | Complete / requested | SR win credit | Paired bootstrap 95% |', '|---|---:|---:|---|']
    for arm in ARMS:
        r=screen['arms'][arm]
        lines.append(f"| {LABEL[arm]} | {r['statuses'].get('complete',0):,} / {r['games']:,} | {interval(r['credit_bounds'])} | {interval(r['paired_bootstrap95_missing_envelope'])} |")
    lines+=['','The screen and confirmation are separate seed sets. They are not pooled. Screen outcomes did not change weights, settings or implementation.', '',
        '## Caps and information exposure','', '| Confirmation arm | Terminal categories | SR credit if all native caps were unknown | Opponent-blind positions: SR / AlphaZero |', '|---|---|---|---|']
    for arm in ARMS:
        r=confirm['arms'][arm];replay=json.loads((BASE/'confirmation'/arm/'replay.json').read_text())
        positions=replay['opponent_blind_positions']
        lines.append(f"| {LABEL[arm]} | {json.dumps(r['terminal_categories'],sort_keys=True)} | {interval(r['cap_unknown_credit_bounds'])} | {positions.get('champion',0):,} / {positions.get('alphazero',0):,} |")
    lines+=['','Native 124-turn outcomes use the unchanged upstream score and purchased-card tie break. They are legitimate native outcomes. The table also gives a sensitivity check that treats those caps as unknown. These results do not assign canonical victories to capped games. Exposure counts are descriptive; they are affected by the agents\' actions.', '',
        '## Validation and runtime','',
        'The new tests check hidden-world input and full800-choice invariance, full reservation support, known public memory, all three reservation tiers, exact privileged features, unordered-set invariance, malformed partitions, exact neural leaf inputs at both actors, and paired statistical bounds. The public worker matches an immutable main worker. Eight full control histories match the old runner in every original non-timing field.', '',
        'Format, strict workspace Clippy, default release tests and all-feature release tests passed. There are 126 all-feature Rust tests, ten information/statistics Python tests, eight existing native tests and seven existing diagnostic tests. Native differential checks match 9,204 positions and 312,879 legal successors across 100 complete regression trajectories. Development validation errors and their corrections are retained in [validation.json](validation.json).', '',
        f"All {audit['games']:,} outcome games and {audit['transitions']:,} native moves passed replay. Replay checks every legal action, chance seed, state, reward and information input. Blind boards are reconstructed from redacted observations; privileged partition hashes match the referee. Replay does not rerun policy search.", '',
        '| Confirmation arm | Eight-worker wall seconds | SR policy seconds, sum | AlphaZero policy seconds, sum | SR simulations | SR inferences |', '|---|---:|---:|---:|---:|---:|']
    for arm in ARMS:
        r=confirm['arms'][arm]
        lines.append(f"| {LABEL[arm]} | {r['wall_seconds']:.2f} | {r['policy_seconds']['champion']:.2f} | {r['policy_seconds']['alphazero']:.2f} | {r['simulations']:,} | {r['inferences']:,} |")
    lines+=['','Policy times are summed elapsed decision times across concurrent games. They are not isolated CPU times. Wall time includes worker startup and excludes later replay and archive checks. Fixed simulation counts are not equal compute. Other research processes shared this host during confirmation. Host details and process-load snapshots are saved with the freeze, [host-load-start.json](host-load-start.json), [host-load-confirmation-start.json](host-load-confirmation-start.json), and [host-load-confirmation-restart.json](host-load-confirmation-restart.json). These times are not isolated throughput measurements.', '',
        '## Audit and reproduction','',
        'See [README.md](README.md) for the workers and commands. Each arm retains its exact schedule, execution log, replay result and raw-record hashes. Lossless gzip chunks preserve the exact merged history; `archives.json` defines their order and hashes and the recovery of each original shard. `restore.py` restores an exact JSONL copy. The original raw files remain ignored in the execution worktree.', '',
        'The report summaries are [screen/summary.json](screen/summary.json) and [confirmation/summary.json](confirmation/summary.json). [final-audit.json](final-audit.json) checks frozen source/binary/model/upstream hashes, every lossless archive, all replay counts and exact statistical summary reruns. `artifact-manifest.json` identifies the final saved report, commands, logs and evidence. No default policy is promoted by this experiment.', '',
        'The first confirmation control process stopped after 4,180 complete games. Its exit result was unavailable when work resumed. Every partial record and log is retained in [interrupted/control/interruption.json](interrupted/control/interruption.json) and lossless shard archives. The full original control schedule was repeated with the same frozen settings and seeds. [interruption-verification.json](interruption-verification.json) checks that all 4,180 repeated games match in every non-timing field. The repeated full schedule is used once in the comparison. No setting or result was selected from the interrupted run.', '']
    (BASE/'REPORT.md').write_text('\n'.join(lines))
    print('Wrote REPORT.md')

if __name__=='__main__':main()
