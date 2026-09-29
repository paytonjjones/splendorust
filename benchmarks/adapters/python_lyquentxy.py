#!/usr/bin/env python3
"""Unpatched lyquentxy Numba opening clone-and-take adapter.

Run with the isolated environment. No model, inference or training imports.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=12345)
    parser.add_argument('--mode', choices=['compiled', 'public-api'], default='compiled')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--target-seconds', type=float)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error('iterations must be positive')
    if args.threads < 1 or args.iterations % args.threads:
        parser.error('threads must be positive and divide iterations')
    if args.repetitions < 1:
        parser.error('repetitions must be positive')
    if args.target_seconds is not None and args.target_seconds <= 0:
        parser.error('target seconds must be positive')
    if args.mode == 'public-api' and args.threads != 1:
        parser.error('public-api supports one thread only')
    startup = time.perf_counter()
    sys.path.insert(0, str(args.root.resolve()))
    import numpy as np
    import numba
    import llvmlite
    from llvmlite import binding as llvm
    from numba import njit
    from splendor.SplendorLogicNumba import Board
    from splendor.SplendorLogic import np_different_gems_up_to_3

    @njit
    def seed_numba(seed):
        np.random.seed(seed)

    @njit(nogil=True)
    def batch(board, state, action, iterations):
        checksum = 0
        for _ in range(iterations):
            board.copy_state(state, True)
            next_player = board.make_move(action, 0, 0)
            checksum += int(board.state[0, 0]) + int(board.state[34, 0]) + next_player
        return checksum

    seed_numba(args.seed & 0xffffffff)
    board = Board(2)
    opening = board.get_state().copy()
    opening_snapshot = opening.copy()
    matches = np.flatnonzero(np.all(np_different_gems_up_to_3[:, :5] == [1, 1, 1, 0, 0], axis=1))
    assert len(matches) == 1
    action = int(30 + matches[0])
    assert board.valid_moves(0)[action]
    batch(board, opening, action, 1)
    expected = opening.copy()
    expected[0, :3] -= 1
    expected[34, :3] += 1
    expected[0, 6] += 1
    assert np.array_equal(board.get_state(), expected), 'unexpected transition'
    assert np.all(opening[0, :6] == [4, 4, 4, 4, 4, 5])
    assert np.all(opening[34:36] == 0)
    boards = [board] + [Board(2) for _ in range(args.threads - 1)]
    pool = ThreadPoolExecutor(max_workers=args.threads) if args.threads > 1 else None
    if pool:
        # Start workers before the steady-state clock. Each task owns its Board.
        list(pool.map(lambda b: batch(b, opening, action, 1), boards))
    initialization_seconds = time.perf_counter() - startup
    if args.mode == 'public-api':
        from splendor.SplendorGame import SplendorGame
        game = SplendorGame()
        result, player = game.getNextState(opening, 0, action, 0)
        assert player == 1 and np.array_equal(result, expected)
    initialization_seconds = time.perf_counter() - startup
    def execute(iterations):
        if args.mode == 'compiled':
            if pool:
                return int(sum(pool.map(lambda b: batch(b, opening, action, iterations // args.threads), boards)))
            return int(batch(board, opening, action, iterations))
        checksum = 0
        for _ in range(iterations):
            result, player = game.getNextState(opening, 0, action, 0)
            checksum += int(result[0, 0]) + int(result[34, 0]) + player
        return checksum
    pilot = None
    if args.target_seconds is not None:
        pilot_iterations = math.ceil(100000 / args.threads) * args.threads
        pilot_start = time.perf_counter()
        assert execute(pilot_iterations) == 5 * pilot_iterations
        pilot_seconds = time.perf_counter() - pilot_start
        args.iterations = max(args.iterations, math.ceil(pilot_iterations * args.target_seconds / pilot_seconds * 1.15 / args.threads) * args.threads)
        pilot = {'iterations': pilot_iterations, 'elapsed_seconds': pilot_seconds,
                 'target_seconds': args.target_seconds, 'calibrated_iterations': args.iterations}
    repetitions = []
    for repetition in range(args.repetitions):
        start = time.perf_counter()
        checksum = execute(args.iterations)
        elapsed = time.perf_counter() - start
        assert checksum == 5 * args.iterations
        assert np.array_equal(opening, opening_snapshot), 'input mutated'
        if args.mode == 'compiled':
            assert all(np.array_equal(b.get_state(), expected) for b in boards)
        else:
            assert np.array_equal(game.board.get_state(), expected)
        repetitions.append({'repetition': repetition, 'elapsed_seconds': elapsed,
                            'transitions_per_second': args.iterations / elapsed,
                            'checksum': checksum})
    if pool:
        pool.shutdown()
    assert checksum == 5 * args.iterations
    assert np.array_equal(opening[0, :6], [4, 4, 4, 4, 4, 5]), 'input mutated'
    report = {
        'engine': 'lyquentxy/splendor', 'workload': 'opening_clone_take_wbg',
        'comparison_group': 'prevalidated_unchecked_opening_clone_take_wbg', 'mode': args.mode,
        'rank_eligible': False,
        'action_validation_inside_timed_loop': False,
        'players': 2, 'threads': args.threads, 'iterations': args.iterations, 'seed': args.seed,
        'elapsed_seconds': elapsed, 'transitions_per_second': args.iterations / elapsed,
        'initialization_and_jit_seconds': initialization_seconds, 'checksum': checksum,
        'repetitions': repetitions,
        'samples': repetitions, 'pilot': pilot,
        'opening_sha256': hashlib.sha256(opening.tobytes()).hexdigest(),
        'validation': {'exact_expected_state': True, 'input_unchanged': True, 'legal_action': True},
        'python': platform.python_version(), 'numpy': np.__version__, 'numba': numba.__version__,
        'llvmlite': llvmlite.__version__, 'llvm': list(llvm.llvm_version_info),
        'adapter_loop_flags': 'Numba njit(nogil=True); no fastmath, no cache; native target default',
        'upstream_flags': 'Pinned upstream helpers retain their own fastmath/cache decorators unchanged',
        'revision': subprocess.check_output(['git', '-C', str(args.root), 'rev-parse', 'HEAD'], text=True).strip(),
        'upstream_patches': [],
        'limits': ['Opening token transition only; randomized markets differ between engines.',
                   'Compiled mode measures Numba hot loop; public-api mode includes Python dispatch.',
                   'Native make_move is unchecked; action validity is checked before timing only.',
                   'No full-game comparison: upstream action set and termination differ.'],
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n')
    print(rendered)


if __name__ == '__main__':
    main()
