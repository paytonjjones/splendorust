"""Archive the exact source/checkpoint basis of AlphaZero pipeline hypotheses."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import torch
from data import ROOT, sha

PIN = '32a27ac1f85d5de2766cc5f60c2bf04e557f7836'
CHECKPOINT = '6a98e0375613ce7f50c87b0f630c4166629fecc13be487f099cfed3def02fa07'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    source = ROOT / 'local/strength/external/alphazero'
    assert subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip() == PIN
    assert not subprocess.check_output(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    sys.path.insert(0, str(source))
    checkpoint = source / 'splendor/pretrained_2players.pt'
    assert sha(checkpoint) == CHECKPOINT
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    files = ['Coach.py', 'MCTS.py', 'GenericNNetWrapper.py', 'main.py',
             'splendor/SplendorGame.py', 'splendor/SplendorLogicNumba.py', 'splendor/SplendorNNet.py']
    needles = {
        'iterative_selfplay': ('Coach.py', 'self.nnet.train(trainExamples)'),
        'recent_replay': ('Coach.py', 'self.trainExamplesHistory.pop(0)'),
        'full_visit_policy': ('Coach.py', 'getActionProb(canonicalBoard, temp=1.)'),
        'root_q_label': ('Coach.py', 'x[4]'),
        'terminal_value': ('Coach.py', 'np.roll(r, -x[2])'),
        'mixed_value_loss': ('GenericNNetWrapper.py', 'targets_V + self.args[\'q_weight\'] * targets_Q'),
        'full_cap_randomization': ('MCTS.py', 'self.rng.random() < self.args.prob_fullMCTS'),
        'full_states_only': ('Coach.py', 'if is_full_search:'),
        'root_noise': ('MCTS.py', 'self.applyDirNoise(Ps, Vs)'),
        'early_stochastic_actions': ('Coach.py', 'action = random_pick(pi, temperature=2'),
        'forced_playout_pruning': ('MCTS.py', 'adjusted_counts = [Nsa-int(math.sqrt'),
        'symmetry': ('splendor/SplendorLogicNumba.py', 'def get_symmetries('),
        'previous_network_gate': ('Coach.py', 'float(nwins) / (pwins + nwins)'),
        'batch_inference': ('Coach.py', 'self.nnet.predict_server'),
        'architecture_v80': ('splendor/SplendorNNet.py', 'elif self.version == 80:'),
    }
    evidence = {}
    for feature, (file, needle) in needles.items():
        matches = [i for i, line in enumerate((source / file).read_text().splitlines(), 1) if needle in line]
        assert matches, (feature, needle)
        evidence[feature] = dict(file=file, lines=matches, evidence='implemented in pinned source')
    metadata = {k: v for k, v in payload.items() if k not in ('state_dict', 'full_model')}
    result = dict(schema='pinned-training-strategy-audit-v1', revision=PIN,
        checkpoint_sha256=CHECKPOINT, metadata=metadata,
        files={file: sha(source / file) for file in files}, features=evidence,
        parameters=sum(v.numel() for k, v in payload['state_dict'].items() if not k.endswith(('running_mean', 'running_var', 'num_batches_tracked'))),
        limits=['Saved settings and current pinned implementation do not prove the full checkpoint training lineage.',
                'Upstream trains value on root Q; it does not train a per-action Q output.',
                'No verified staged-budget lineage is retained in this checkpoint.',
                'Upstream native rules and private-information inputs differ from canonical SplendoRust.'],
        value_formula='(terminal_signed + q_weight * root_Q_signed) / (1 + q_weight)',
        policy_formula='normalized root visits after optional forced-playout pruning, temperature 1',
        action_formula='sample policy with temperature 2 before total turn threshold; saved later temperature 0.8',
        inference_config='Frozen benchmark overrides full probability to1 and forced_playouts toFalse; training metadata remains distinct.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assert not args.output.exists()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(revision=PIN, checkpoint_sha256=CHECKPOINT, settings=metadata)))


if __name__ == '__main__':
    main()
