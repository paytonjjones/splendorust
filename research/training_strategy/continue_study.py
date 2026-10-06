"""Advance registered stages after evidence checks, without repeating a run."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from audit_targets import audit
from data import ROOT, sha
from runtime import command_run
from status import process
from strategy_summary import canonical
from resources import evaluation_resources


SCREENS = {
    'first': [('screen-onehot', 5431000000), ('screen-visits', 5432000000),
              ('screen-visits-q', 5433000000), ('screen-visits-v-onehot', 5434000000),
              ('screen-q-v-visits', 5435000000)],
    'second': [('iterative-v-static', 5461000000), ('frozen-v-static', 5462000000),
               ('iterative-v-frozen', 5463000000), ('iterative-v-original', 5464000000),
               ('frozen-v-original', 5465000000)],
    'efficiency': [('pcr-v-full', 5481000000), ('pcr-v-original', 5482000000)],
}
CORPORA = {'first': [('train', 2000), ('dev', 400)],
           'second': [('iterative-data', 2000), ('frozen-data', 2000), ('dev', 400)],
           'efficiency': [('pilot-full', 64), ('pilot-pcr', 64), ('pcr-data', None)]}
FITS = {'first': ['onehot', 'visits', 'visits-q'],
        'second': ['iterative', 'frozen'], 'efficiency': ['pcr']}


def load(path):
    return json.loads(Path(path).read_text())


def unchanged():
    assert sha(ROOT / 'research/entity_baseline/model.pt') == (
        'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84')
    assert (ROOT / 'research/CHAMPION.json').read_bytes() == subprocess.check_output(
        ['git', 'show', '7367b05:research/CHAMPION.json'], cwd=ROOT)


def verify(name, directory):
    """Validate retained outcomes, costs, settings, weights, and source receipts."""
    directory = Path(directory).resolve()
    completion = load(directory / 'complete.json')
    plan = load(directory / 'plan.json')
    resource = completion.get('resource_amendment', plan.get('resource_amendment', {'eval_threads': 32}))
    workers = resource['eval_threads']
    approved = evaluation_resources(workers)
    if workers == 64:
        assert resource['resource_parity_sha256'] == approved['resource_parity_sha256']
    unchanged()
    assert all(sha(ROOT / path) == digest for path, digest in plan['source_files'].items())
    result = dict(stage=name, completion_sha256=sha(directory / 'complete.json'),
                  plan_sha256=sha(directory / 'plan.json'), screens={}, corpora={}, fits={})
    for label, games in CORPORA[name]:
        checked = audit(directory / label)
        collected = load(directory / label / 'complete.json')
        assert collected['all_games_replayed']
        assert games is None or collected['games'] == games
        assert checked['full_visit_totals'] == [256]
        result['corpora'][label] = checked
    for label in FITS[name]:
        fit = load(directory / label / 'manifest.json')
        assert sha(directory / label / 'model.pt') == fit['checkpoint_sha256']
        assert sha(directory / label / 'runtime.pt') == fit['runtime_sha256']
        assert load(directory / ('fit-' + label) / 'exit.json')['returncode'] == 0
        assert fit['plan']['epochs'] == 4 and fit['plan']['batch'] == 512
        result['fits'][label] = dict(checkpoint_sha256=fit['checkpoint_sha256'],
                                   runtime_sha256=fit['runtime_sha256'])
    source_ids = set()
    for label, seed in SCREENS[name]:
        screen = directory / label / 'screen.json'
        evidence = canonical(screen)
        report = load(screen)
        assert evidence['games'] == 2000 and evidence['seed'] == seed
        assert report['players'] == 2 and report['threads'] == workers
        assert report['engine'] == 'splendorust-v2' and report['reproducible']
        config = report['run_config']
        assert config['names'] == ['flywheel-gumbel-candidate', 'flywheel-gumbel']
        assert config['search']['iterations'] == 128 and config['search']['depth'] == 16
        assert config['search']['time_budget'] is None
        command = directory / (label + '-command')
        assert load(command / 'exit.json')['returncode'] in (0, 2)
        run = load(directory / label / 'run.json')
        assert run['seed'] == seed and run['confirm'] == 0
        for tool, digest in run['evidence_tools_sha256'].items():
            assert sha(ROOT / 'scripts' / tool) == digest
        build = load(directory / label / 'build.json')
        assert sha(build['executable']) == build['binary_sha256']
        source_ids.add(evidence['source_id'])
        result['screens'][label] = evidence
    assert len(source_ids) == 1
    assert completion['official_champion_unchanged']
    if name == 'efficiency':
        budget = load(directory / 'budget.json')
        assert 0 <= budget['overshoot'] <= .02 and budget['whole_last_chunk_accounted']
        assert result['corpora']['pcr-data']['receipt']['eligible_rows'] > 0
    return result


def wait_finished(directory):
    """Never restart an existing run; stop when its process is actually absent."""
    directory = Path(directory)
    identities = [str(directory), str(directory.resolve())]
    if directory.is_relative_to(ROOT):
        identities.append(str(directory.relative_to(ROOT)))
    while True:
        progress_path = directory / 'progress.json'
        if progress_path.exists():
            try:
                state = load(progress_path)
            except json.JSONDecodeError:
                time.sleep(1)
                continue
        else:
            state = load(directory / 'plan.json')
        current = process(state['pid'])
        if current['live']:
            assert any(script in current['command'] for script in (
                'research/training_strategy/run_', 'research/training_strategy/resume_first.py'))
            assert any(identity in current['command'] for identity in identities)
            time.sleep(30)
            continue
        assert (directory / 'complete.json').exists(), f'Run stopped without completion: {directory}'
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--eval-threads', type=int, choices=(32, 64), default=32)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    resource = evaluation_resources(args.eval_threads)
    out.mkdir(parents=True, exist_ok=False)
    lock = (ROOT / 'local/research/training-strategy-chain.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
    plan = dict(pid=os.getpid(), started_at=time.time(), root=str(root),
                controller_sha256=sha(__file__),
                resource_amendment=resource,
                policy='Never repeat an existing stage; stop on failed evidence checks.')
    (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    checked = []

    def progress(stage):
        state = dict(pid=os.getpid(), stage=stage, checked_stages=checked, updated_at=time.time())
        temporary = out / 'progress.json.partial'
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(out / 'progress.json')
        print(json.dumps(state), flush=True)

    try:
        first, second, efficiency = (root / name for name in ('first', 'second', 'efficiency'))
        launches = {
            'second': ['run_iterative.py', '--first', first, '--output', second],
            'efficiency': ['run_efficiency.py', '--first', first, '--second', second, '--output', efficiency,
                           '--eval-threads', args.eval_threads],
            'milestone': ['run_milestone.py', '--first', first, '--second', second,
                          '--efficiency', efficiency, '--output', root / 'milestone', '--eval-threads', args.eval_threads],
        }
        for name in ('first', 'second', 'efficiency', 'milestone'):
            directory = root / name
            progress('wait-' + name)
            if not directory.exists():
                assert name != 'first', 'First stage must already exist'
                launch = launches[name]
                command_run([sys.executable, '-u', Path(__file__).with_name(launch[0]),
                             *launch[1:]], out / ('launch-' + name))
            wait_finished(directory)
            progress('verify-' + name)
            if name == 'milestone':
                unchanged()
                result = load(directory / 'complete.json')
                assert sha(Path(__file__).with_name('MILESTONE.md')) == result['plan']['rule_sha256']
                gate = directory / 'gate'
                if gate.exists():
                    result['checked_screen'] = canonical(gate / 'screen.json')
                    if (gate / 'confirm.json').exists():
                        result['checked_confirmation'] = canonical(gate / 'confirm.json')
            else:
                result = verify(name, directory)
            (out / (name + '-verified.json')).write_text(json.dumps(result, indent=2) + '\n')
            checked.append(name)
        progress('await-final-report-and-archive')
        (out / 'complete.json').write_text(json.dumps(dict(plan=plan, checked_stages=checked,
            finished_at=time.time(), full_goal_complete=False,
            remaining='Final cost accounting, archive/restore, recommendation and handoff.'), indent=2) + '\n')
    except BaseException as error:
        (out / 'failure.json').write_text(json.dumps(dict(pid=os.getpid(), error=repr(error),
            checked_stages=checked, failed_at=time.time()), indent=2) + '\n')
        raise


if __name__ == '__main__':
    main()
