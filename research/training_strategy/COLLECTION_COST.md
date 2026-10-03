# Collection cost

The completed 4-worker pilot is much slower per game than the earlier frozen
Entity tests. The workloads and batch use explain much of the difference.
The separate effect of shared GPU load has not been measured.

| Workload | Games | Seconds | Games/second | Model/search settings |
|---|---:|---:|---:|---|
| Current collection pilot | 64 | 3,148.253 | 0.02033 | Both seats Entity; PUCT256; 4 workers |
| Current collection pilot | 64 | 1,064.890 | 0.06010 | Both seats Entity; PUCT256; 8 workers |
| Current collection pilot | 64 | 550.458 | 0.11627 | Both seats Entity; PUCT256; 16 workers |
| Current collection pilot | 64 | 309.926 | 0.20650 | Both seats Entity; PUCT256; 32 workers |
| Frozen canonical screen | 2,000 | 1,727.788 | 1.15755 | Entity versus E81; Gumbel128; 32 workers |
| Frozen native policy screen | 2,000 | 92.861 | 21.53763 | Entity versus E81; no search; 14 workers |

The 4-worker pilot time per game is 56.94 times the frozen canonical screen time.
This is a workload comparison. It does not measure an engine regression.
The native policy screen has different rules and zero search simulations.

The current collector made 860,927 Entity inferences for 64 games:
13,451.98 calls/game and 273.46 calls/second. It recorded 3,586 full-search
positions, each with 256 root visits. Both seats use the Transformer.
In the prior native policy screen, Entity made 55,598 calls for 2,000 games:
27.80 calls/game. In the prior canonical screen, only one seat used Entity;
the other used the smaller E81 model. Each had 128 search simulations.

`research/architecture_pivots/service.py` always runs a 32-row tensor batch.
It pads missing requests with zeros to keep tensor arithmetic independent of
queue occupancy. Each game issues one inference request at a time. Four
active games therefore provide at most four useful rows and leave at least
28 padded rows. The low worker count is an expensive scaling diagnostic.
Registered training collection uses 32 workers. All four pilots have passed
the exact target and history hash checks. Request rates alone do not prove
game throughput.

The completed 8-worker pilot has 2.956 times the 4-worker game throughput,
with 808.47 model calls/second. All 64 games finished. The raw target rows,
packed model inputs and ordered replay records have identical SHA256 hashes
at both worker counts. The independent terminal-label audit also passed.
This is a measured shared-host scaling result; changing host load prevents
an isolated attribution of the whole speed increase to worker count.

The 16-worker pilot completed all 64 games in 550.458 seconds, with 1,564.02
model calls/second. This is 1.935 times the 8-worker game throughput. Its
target rows, packed inputs and ordered replay records are byte-identical
to the 4- and 8-worker outputs. All terminal labels match their game records.

The 32-worker pilot completed all 64 games in 309.926 seconds, with 2,777.85
model calls/second. This is 1.776 times the 16-worker game throughput and
10.158 times the 4-worker throughput. All four runs have identical target,
packed-input and ordered replay bytes. Each terminal-label audit passed.
The controller then started the registered 2,000-game training collection.

Extrapolating this pilot gives 3.228 hours to collect the first 2,000 training
and 400 development games. This is an estimate, not a completed cost result:
new seeds, game lengths, batch tails and shared GPU load can change it. Fits
and fresh canonical strength screens add further cost. The measured cost
supports testing cap randomization, but does not prove it saves cost per
useful target or improves playing strength. Those need controlled results.

The original architecture study's Entity trainer was active during most of
the 4-worker pilot, as recorded in `first/host-start.json`. A separate history
inference service was active during the later 8-worker run. These jobs were
left unchanged. All wall times are from a shared host; there is no isolated
measurement of the contention cost. Capture-on/off tests show that saving
root search targets adds no simulations or model inferences.

Evidence:

- `local/research/training-strategy/first/scaling-4/complete.json`;
  SHA256 `60597b7cfeea3b6b1f442edcd34476f98061960ee6e5552e4788c44f4abb731e`.
- `pilot-4-target-audit.json` independently checks the labels against retained
  game records. Pilot rows are excluded from training and strength tests.
- `local/research/training-strategy/first/scaling-8/complete.json`;
  SHA256 `3717b8c1fb9178e5ba660f9e228ceda4d4a63910f26f731f7ec8dda9088a6ca8`.
  Its independent label check is in `pilot-8-target-audit.json`.
- `local/research/training-strategy/first/scaling-16/complete.json`;
  SHA256 `e16d2f985ec4d307f18f6d05efdcf9ac0cd5f768c6dc5a78bc0075595920ce69`.
  Its independent label check is in `pilot-16-target-audit.json`.
- `local/research/training-strategy/first/scaling-32/complete.json`;
  SHA256 `b80d6baaaf4ea8b10ccac14ffdb96d3be9ecbca414bff2a355cd03f05f231dc7`.
  Its independent label check is in `pilot-32-target-audit.json`.
- Frozen `research/entity_baseline/expanded-entity-gate/screen.json`;
  SHA256 `56b568fcde1770f9bf078fdc8091198c03ae278e855c21800b4a63edb2a4d4a5`.
- Frozen `research/entity_baseline/expanded-native-entity-champion/summary.json`
  and `research/entity_baseline/entity-service-probe.json`.

The frozen service probe measured 526 calls/second with four clients and
3,474 calls/second with 32 clients. It was a short tensor-service probe, so
it cannot replace the current whole-game scaling measurements.

## Completed training collection

The registered 32-worker training collection completed all 2,000 games in
8,865.911 seconds (2.463 hours): 0.22558 games/second and 4.433 seconds/game.
It used 26,751,234 Entity model calls and 28,432,640 search simulations. All
games replayed successfully; none were blocked or capped. These are collection
costs on the shared host. Fit, development and strength-screen costs are still
pending.

`training-target-audit.json` checks all 111,136 retained rows against their
ordered game records. It identifies 111,065 eligible full-search targets and
71 excluded rows. Every eligible target has 256 visits. Legal/explored masks,
Q conservation and terminal labels pass. The raw row SHA256 is
`848df084647a02ebd2ade4892b8e4ee42cafdccee66d66447054558db7f79e76`;
the packed-input SHA256 is
`41e6e66d01f791b4c3a96b7721e14cfec0ab5f6452230a1e48698745aaa92778`.
The receipt includes the ordered-history and completion hashes. These label
diagnostics do not establish playing strength.

The separate 400-game development collection finished in 2,129.709 seconds
(35.5 minutes), with 22,283 eligible targets and zero incomplete games. The
combined training/development collection cost is 3.054 hours. The three
four-epoch fits took 243.094 seconds (onehot), 240.749 seconds (visits), and
243.393 seconds (visits-Q). The completed onehot canonical screen took
7,449.696 seconds (2.069 hours) for 2,000 games. Collection, fit and evaluation
are separate costs; only one strength comparison is complete at this stage.

## Resource request and 64-worker check

The user requested more Mac resources on 2026-10-03. A live GPU sample showed
75% device utilization; the Rust collector spent most of its time waiting for
the single inference service. The excluded resource pilots used the same
fixed 32-row GPU batches, frozen weights and search settings. The main
frozen-teacher collection continued during every pilot. Treat the times as
shared-host costs, not isolated hardware scaling.

| Pilot, 64 games | 32 workers | 64 workers | Throughput ratio |
|---|---:|---:|---:|
| Full256 collection | 447.051 s | 351.536 s | 1.272 |
| Gumbel128 arena | 267.462 s | 180.686 s | 1.480 |

Both collection runs match the original 32-worker pilot's raw, input and
history hashes exactly. Both arena runs have identical ordered game records
and trajectory hashes, record-set SHA256 recorded in
`resource-scaling-evidence.json`. These pilots are excluded from learning and
strength claims. The four pilot commands cost 1,246.735 measured workload
seconds, plus their preparation and command overhead; retain those costs.

The measured arena gain supports using 64 workers for remaining evaluation.
The new common development corpus also uses 64. Existing current/frozen
generation corpora and future PCR collection keep 32 workers for matched
collection costs. Search budgets, seeds, training updates and model arithmetic
stay fixed. The live frozen collector was adopted, so its games are not repeated.
