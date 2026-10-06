"""Isolate cap randomization at a retained, measured inference-call budget."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from data import ROOT, prepare, sha
from efficiency_data import assemble
from run_iterative import choose
from runtime import Runtime, command_run
from strategy_summary import canonical
from resources import evaluation_resources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=19620)
    parser.add_argument('--device', choices=('mps', 'cpu'), default='mps')
    parser.add_argument('--eval-threads', type=int, choices=(32, 64), default=32)
    args = parser.parse_args()
    resource = evaluation_resources(args.eval_threads)
    first, second, out = args.first.resolve(), args.second.resolve(), args.output.resolve()
    assert (first / 'complete.json').exists() and (second / 'complete.json').exists()
    selection = choose(first)
    previous = json.loads((second / 'plan.json').read_text())
    assert selection == previous['selection']
    parent = first / selection['arm'] / 'model.pt'
    teacher = first / selection['arm'] / 'runtime.pt'
    frozen = ROOT / 'research/entity_baseline/model.pt'
    assert sha(parent) == previous['parent_sha256']
    assert sha(teacher) == previous['current_sha256']
    assert sha(frozen) == 'cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84'
    for study in (first, second):
        recorded = json.loads((study / 'plan.json').read_text())
        assert all(sha(ROOT / path) == digest for path, digest in recorded['source_files'].items())
    full_data = json.loads((second / 'iterative-data/complete.json').read_text())
    full_fit = json.loads((second / 'iterative/manifest.json').read_text())
    assert full_fit['plan']['parent_sha256'] == sha(parent)
    assert full_fit['plan']['arm'] == selection['arm']
    assert full_fit['plan']['epoch_rows'] == previous['epoch_rows']
    assert full_fit['plan']['epochs'] == 4 and full_fit['plan']['batch'] == 512
    assert sha(second / 'iterative/runtime.pt') == full_fit['runtime_sha256']
    assert sha(ROOT / 'target/release/examples/rich_selfplay') == previous['collector_sha256']
    assert full_data['inferences'] > 0
    lock = (ROOT / 'local/research/training-strategy.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.write(str(os.getpid())); lock.flush()
    out.mkdir(parents=True, exist_ok=False)
    champion = ROOT / 'research/CHAMPION.json'
    champion_before = champion.read_bytes()
    collector = ROOT / 'target/release/examples/rich_selfplay'
    sources = [Path(__file__), Path(__file__).with_name('efficiency_data.py'),
               Path(__file__).with_name('EFFICIENCY.md'), Path(__file__).with_name('audit_targets.py'),
               Path(__file__).with_name('strategy_train.py'), Path(__file__).with_name('data.py'),
               Path(__file__).with_name('runtime.py'), ROOT / 'research/architecture_pivots/models.py']
    sources.append(Path(__file__).with_name('strategy_summary.py'))
    sources.append(Path(__file__).with_name('resources.py'))
    plan = dict(schema='cap-randomization-study-v1', pid=os.getpid(), started_at=time.time(),
                source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                selection=selection, resource_amendment=resource,
                teacher_sha256=sha(teacher), parent_sha256=sha(parent),
                collector_sha256=sha(collector), full_control_data=full_data,
                target_inferences=full_data['inferences'], maximum_call_overshoot=.02,
                maximum_games=20000, chunk_games=64, full_probability=.25, cheap_iterations=64,
                iterations=256, threads=32, depth=16, epoch_rows=previous['epoch_rows'],
                setup_master=5440000000, policy_master=9440000000,
                pilot_setup_master=5480000000, pilot_policy_master=9480000000,
                source_files={str(path.relative_to(ROOT)): sha(path) for path in sources})
    (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    stages = []

    def progress(stage, **work):
        receipt = dict(stage=stage, pid=os.getpid(), updated_at=time.time(), completed_stages=stages, **work)
        (out / 'progress.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)

    def collect(runtime, name, directory, master, policy, probability):
        progress(name)
        result = command_run([collector, '--model', runtime.descriptors[13], '--output', directory,
                              '--games', 64, '--seed', master, '--policy-seed', policy,
                              '--threads', 32, '--iterations', 256, '--cheap-iterations', 64,
                              '--full-probability', probability, '--depth', 16], out / (name + '-command'))
        stages.append(name)
        return result, json.loads((directory / 'complete.json').read_text())

    try:
        pilots = {}
        with Runtime([(13, teacher)], out / 'collection-service', args.port, args.device) as runtime:
            for name, probability in [('pilot-full', 1.0), ('pilot-pcr', .25)]:
                _, receipt = collect(runtime, name, out / name, 5480000000, 9480000000, probability)
                prepare(out / name)
                pilots[name] = receipt
            parts = []
            inferences = games = 0
            collection_start = time.monotonic()
            while inferences < plan['target_inferences']:
                assert games + 64 <= plan['maximum_games'], 'PCR generation reached its episode bound'
                name = f'pcr-chunk-{games:06d}'
                directory = out / 'chunks' / name
                _, receipt = collect(runtime, name, directory, 5440000000 + games, 9440000000 + games, .25)
                assert receipt['seed'] == 5440000000 + games
                assert receipt['policy_seed'] == 9440000000 + games
                parts.append(directory)
                inferences += receipt['inferences']
                games += receipt['games']
                progress('pcr-budget', games=games, inferences=inferences,
                         target_inferences=plan['target_inferences'])
            overshoot = inferences / plan['target_inferences'] - 1
            (out / 'budget.json').write_text(json.dumps(dict(inferences=inferences, games=games,
                target_inferences=plan['target_inferences'], overshoot=overshoot,
                whole_last_chunk_accounted=True), indent=2) + '\n')
            assert overshoot <= .02, 'PCR call budget overshoot exceeds registered tolerance'
            completion = assemble(parts, out / 'pcr-data')
            assert completion['inferences'] == inferences
            collection_seconds = time.monotonic() - collection_start
        progress('fit-pcr')
        fit_result = command_run([sys.executable, Path(__file__).with_name('strategy_train.py'),
                                  '--arm', selection['arm'], '--parent', parent,
                                  '--train', first / 'train', '--train', out / 'pcr-data',
                                  '--dev', second / 'dev', '--epoch-rows', previous['epoch_rows'],
                                  '--output', out / 'pcr', '--device', args.device], out / 'fit-pcr')
        stages.append('fit-pcr')
        models = [(13, frozen), (14, second / 'iterative/runtime.pt'), (15, out / 'pcr/runtime.pt')]
        with Runtime(models, out / 'arena-service', args.port, args.device) as runtime:
            for name, opponent, seed in [('pcr-v-full', 14, 5481000000), ('pcr-v-original', 13, 5482000000)]:
                progress(name)
                environment = dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[15]),
                                   SPLENDOR_BEST_MODEL=str(runtime.descriptors[opponent]))
                command_run([sys.executable, ROOT / 'scripts/promote.py', '--candidate', 'flywheel-gumbel-candidate',
                             '--baseline', 'flywheel-gumbel', '--players', 2, '--screen', 2000, '--confirm', 0,
                             '--seed', seed, '--threads', args.eval_threads, '--iterations', 128, '--depth', 16,
                             '--output', out / name], out / (name + '-command'), environment, accepted=(0, 2))
                canonical(out / name / 'screen.json')
                stages.append(name)
        costs = dict(pilots=pilots, full_control=full_data,
                     pcr_data=completion, pcr_collection_wall_seconds=collection_seconds,
                     pcr_fit_command_seconds=fit_result['seconds'], full_fit_seconds=full_fit['seconds'],
                     common_dev=json.loads((second / 'dev/complete.json').read_text()),
                     call_budget_overshoot=overshoot,
                     direct=canonical(out / 'pcr-v-full/screen.json'),
                     pcr_original=canonical(out / 'pcr-v-original/screen.json'),
                     full_original=canonical(second / 'iterative-v-original/screen.json'),
                     limits=['Useful inference calls matched; wall time and padded FLOPs are not matched.',
                             'Pilot, service setup and arena costs are separate experiment costs.'])
        def command_seconds(directory):
            return json.loads((directory / 'exit.json').read_text())['seconds']
        first_generation_seconds = (
            json.loads((first / 'train/complete.json').read_text())['seconds'] +
            json.loads((first / 'dev/complete.json').read_text())['seconds'] +
            command_seconds(first / ('fit-' + selection['arm'])))
        common_seconds = first_generation_seconds + costs['common_dev']['seconds']
        production_seconds = dict(
            full=common_seconds + full_data['seconds'] + command_seconds(second / 'fit-iterative'),
            pcr=common_seconds + completion['seconds'] + fit_result['seconds'])
        costs['production_seconds'] = production_seconds
        costs['production_seconds_basis'] = (
            'Collector seconds plus fit command seconds from frozen Entity through two generations; '
            'excludes preparation, pilots, service setup and strength tests. PCR collection wall time is separate.')
        costs['credit_gain_points_per_production_hour_bounds'] = {
            name: [100 * (credit - .5) / (production_seconds[name] / 3600)
                   for credit in costs[name + '_original']['credit_bounds']]
            for name in ('full', 'pcr')}
        (out / 'cost.json').write_text(json.dumps(costs, indent=2) + '\n')
        assert all(sha(ROOT / path) == digest for path, digest in plan['source_files'].items())
        assert champion.read_bytes() == champion_before
        progress('complete')
        (out / 'complete.json').write_text(json.dumps(dict(plan=plan, stages=stages,
            completed_at=time.time(), official_champion_unchanged=True), indent=2) + '\n')
    except BaseException as error:
        (out / 'failure.json').write_text(json.dumps(dict(error=repr(error), stages=stages,
            pid=os.getpid(), failed_at=time.time()), indent=2) + '\n')
        raise
    finally:
        assert champion.read_bytes() == champion_before


if __name__ == '__main__':
    main()
