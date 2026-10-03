"""Adopt the live corpus collector and increase verified evaluation concurrency."""
import argparse
import fcntl
import json
import os
import signal
import sys
import time
from pathlib import Path
from audit_targets import audit
from data import ROOT, prepare, sha
from resources import evaluation_resources
from runtime import Runtime, command_run
from status import process
from strategy_summary import canonical


def read(path):
    return json.loads(Path(path).read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--first', type=Path, required=True)
    ap.add_argument('--second', type=Path, required=True)
    ap.add_argument('--recovery', type=Path, required=True)
    ap.add_argument('--eval-threads', type=int, choices=(32, 64), default=64)
    args = ap.parse_args()
    first, out, recovery = args.first.resolve(), args.second.resolve(), args.recovery.resolve()
    resource = evaluation_resources(args.eval_threads)
    plan = read(out / 'plan.json')
    previous = read(out / 'progress.json')
    assert previous['stage'] == 'frozen-data' and previous['completed_stages'] == ['iterative-data']
    assert not process(previous['pid'])['live']
    assert all(sha(ROOT / name) == digest for name, digest in plan['source_files'].items())
    assert not (out / 'dev').exists(), 'Do not repeat development collection'
    lock = (ROOT / 'local/research/training-strategy.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
    recovery.mkdir(parents=True, exist_ok=False)
    sources = {str(Path(__file__).relative_to(ROOT)): sha(__file__),
               'research/training_strategy/resources.py': sha(Path(__file__).with_name('resources.py')),
               'research/training_strategy/RESOURCE_AMENDMENT.md': sha(Path(__file__).with_name('RESOURCE_AMENDMENT.md'))}
    amendment = dict(resource, pid=os.getpid(), started_at=time.time(),
                     original_progress=previous, original_plan_sha256=sha(out / 'plan.json'),
                     generation_collection_threads=32, development_threads=args.eval_threads, source_files=sources,
                     reason='User authorized more Mac resources; preserve live collection and increase evaluation workers after parity checks.')
    (recovery / 'plan.json').write_text(json.dumps(amendment, indent=2) + '\n')
    champion = ROOT / 'research/CHAMPION.json'; before = champion.read_bytes()
    stages = list(previous['completed_stages'])

    def progress(stage):
        state = dict(pid=os.getpid(), stage=stage, completed_stages=stages,
                     recovery=str(recovery), updated_at=time.time())
        temporary = out / 'progress.json.partial'
        temporary.write_text(json.dumps(state, indent=2) + '\n'); temporary.replace(out / 'progress.json')
        print(json.dumps(state), flush=True)

    try:
        progress('adopt-frozen-data')
        saved = read(out / 'frozen-data-command/process.json')
        while True:
            live = process(saved['pid'], saved['command'])
            if not live['live']:
                break
            assert live['identity_matches']
            time.sleep(15)
        collected = read(out / 'frozen-data/complete.json')
        assert collected['games'] == 2000 and collected['all_games_replayed']
        assert collected['seed'] == 5440000000 and collected['policy_seed'] == 9450000000
        assert collected['threads'] == 32 and collected['iterations'] == 256
        assert collected['depth'] == 16 and collected['world_pool'] == 3
        checked = audit(out / 'frozen-data')
        # The original parent was deliberately stopped, so its wait status may
        # be unavailable. Retain that gap; do not fabricate an exit code.
        (recovery / 'adopted-frozen-data.json').write_text(json.dumps(dict(
            original_process=saved, completion_sha256=sha(out / 'frozen-data/complete.json'),
            original_exit_receipt_present=(out / 'frozen-data-command/exit.json').exists(),
            process_exit_code=None, verified_complete_corpus=checked), indent=2) + '\n')
        stages.append('frozen-data')
        service = read(out / 'collection-service/run.json')
        assert service['models']['13']['checkpoint_sha256'] == plan['frozen_sha256']
        assert service['models']['14']['checkpoint_sha256'] == plan['current_sha256']
        live = process(service['pid'], service['command'])
        if live['live']:
            assert live['identity_matches']
            os.kill(service['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 30
            while process(service['pid'])['live']:
                assert time.monotonic() < deadline, 'Old owned service did not stop'
                time.sleep(.2)
        frozen = ROOT / 'research/entity_baseline/model.pt'
        assert sha(ROOT / 'target/release/examples/rich_selfplay') == plan['collector_sha256']
        arm = plan['selection']['arm']
        parent, current = first / arm / 'model.pt', first / arm / 'runtime.pt'
        assert sha(parent) == plan['parent_sha256'] and sha(current) == plan['current_sha256']
        assert sha(frozen) == plan['frozen_sha256']
        progress('dev')
        with Runtime([(13, frozen)], recovery / 'dev-service') as runtime:
            command_run([ROOT / 'target/release/examples/rich_selfplay', '--model', runtime.descriptors[13],
                         '--output', out / 'dev', '--games', 400, '--seed', 5450000000,
                         '--policy-seed', 9460000000, '--threads', args.eval_threads, '--iterations', 256,
                         '--depth', 16], out / 'dev-command')
            prepare(out / 'dev')
        stages.append('dev')
        for label in ('iterative', 'frozen'):
            progress('fit-' + label)
            command_run([sys.executable, Path(__file__).with_name('strategy_train.py'), '--arm', arm,
                         '--parent', parent, '--train', first / 'train', '--train', out / (label + '-data'),
                         '--dev', out / 'dev', '--epoch-rows', plan['epoch_rows'], '--output', out / label,
                         '--device', 'mps'], out / ('fit-' + label))
            stages.append('fit-' + label)
        models = [(13, frozen), (14, current), (15, out / 'iterative/runtime.pt'), (16, out / 'frozen/runtime.pt')]
        comparisons = [('iterative-v-static', 15, 14, 5461000000), ('frozen-v-static', 16, 14, 5462000000),
                       ('iterative-v-frozen', 15, 16, 5463000000), ('iterative-v-original', 15, 13, 5464000000),
                       ('frozen-v-original', 16, 13, 5465000000)]
        with Runtime(models, out / 'arena-service') as runtime:
            for label, candidate, baseline, seed in comparisons:
                progress(label)
                environment = dict(SPLENDOR_CANDIDATE_MODEL=str(runtime.descriptors[candidate]),
                                   SPLENDOR_BEST_MODEL=str(runtime.descriptors[baseline]))
                command_run([sys.executable, ROOT / 'scripts/promote.py', '--candidate', 'flywheel-gumbel-candidate',
                             '--baseline', 'flywheel-gumbel', '--players', 2, '--screen', 2000, '--confirm', 0,
                             '--seed', seed, '--threads', args.eval_threads, '--iterations', 128, '--depth', 16,
                             '--output', out / label], out / (label + '-command'), environment, accepted=(0, 2))
                canonical(out / label / 'screen.json')
                stages.append(label)
        assert all(sha(ROOT / name) == digest for name, digest in {**plan['source_files'], **sources}.items())
        assert champion.read_bytes() == before
        progress('complete')
        (out / 'complete.json').write_text(json.dumps(dict(plan=plan, stages=stages,
            resource_amendment=amendment, completed_at=time.time(), official_champion_unchanged=True), indent=2) + '\n')
    except BaseException as error:
        (recovery / 'failure.json').write_text(json.dumps(dict(error=repr(error), pid=os.getpid(),
            stages=stages, failed_at=time.time()), indent=2) + '\n')
        raise
    finally:
        assert champion.read_bytes() == before


if __name__ == '__main__':
    main()
