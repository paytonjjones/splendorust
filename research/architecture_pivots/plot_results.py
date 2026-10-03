"""Plot checked fit and completed canonical screens from the result catalog."""
import json
import hashlib
import platform
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE/'result-catalog.json').read_text())
    kinds = ['small', 'small-cold-mps', 'capacity', 'entity', 'history']
    labels = ['Small, warm', 'Small, cold', 'Residual', 'Entity', 'History']
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    colors = ['#687487', '#087f8c']
    for scale, color, offset in [('initial', colors[0], -.13), ('expanded', colors[1], .13)]:
        xs, accuracy, brier = [], [], []
        for i, kind in enumerate(kinds):
            key = kind if scale == 'initial' else 'expanded-'+kind.replace('-mps', '')
            fit = data['fit'].get(key)
            if not fit or not fit['complete']:
                continue
            xs.append(i+offset)
            accuracy.append(100*fit['selected']['canonical']['policy_accuracy'])
            brier.append(fit['selected']['canonical']['outcome_brier'])
        axes[0].plot(xs, accuracy, 'o-', color=color, label=scale.capitalize())
        axes[1].plot(xs, brier, 'o-', color=color)
        for i, kind in enumerate(kinds):
            key = kind.replace('-mps', '')+'-gate'
            if scale == 'expanded':
                key = 'expanded-'+key
            run = data['strength'].get(key)
            if not run:
                continue
            lo, hi = run['ci95']
            y = 100*run['credit']
            axes[2].errorbar(i+offset, y, yerr=[[max(0, y-100*lo)], [max(0, 100*hi-y)]],
                             fmt='o', color=color, capsize=4)
            if run['incomplete']:
                axes[2].annotate('*', (i+offset, y), xytext=(6, 3), textcoords='offset points')
    axes[0].set_title('Held-out policy accuracy')
    axes[0].set_ylabel('Canonical accuracy (%) — higher is better')
    axes[1].set_title('Held-out outcome Brier')
    axes[1].set_ylabel('Mean squared probability error — lower is better')
    axes[2].set_title('Fresh canonical search screens vs E81')
    axes[2].set_ylabel('Win credit (%) with 95% interval')
    axes[2].axhline(50, linestyle='--', color='#999999', linewidth=1)
    axes[2].set_ylim(0, 100)
    for ax in axes:
        ax.set_xticks(np.arange(len(kinds)), labels, rotation=25, ha='right')
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].legend(frameon=False)
    fig.suptitle('Matched architecture trials: 6,000 vs 30,000 training setups\n'
                 'Same dev set; 12 epochs per base fit; 2,000 search games per screen; Gumbel128', fontsize=12)
    fig.text(.5, -.04, 'History uses 12 extra epochs. * One unfinished game; conservative P2.1 bounds retained. '
             'Data expansion also increases updates. Confirmation results are reported separately.', ha='center', fontsize=9)
    fig.savefig(HERE/'architecture-results.png', dpi=180, bbox_inches='tight')
    fig.savefig(HERE/'architecture-results.svg', bbox_inches='tight')
    plt.close(fig)
    receipt = dict(matplotlib=matplotlib.__version__, python=platform.python_version(),
                   catalog_sha256=hashlib.sha256((HERE/'result-catalog.json').read_bytes()).hexdigest(),
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    receipt['outputs'] = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                          for name in ['architecture-results.png', 'architecture-results.svg']}
    (HERE/'architecture-figure.json').write_text(json.dumps(receipt, indent=2)+'\n')


if __name__ == '__main__':
    main()
