# Frozen expanded Entity Transformer

This is a reusable research baseline. It is the exact parent of the ongoing
history/opponent/belief experiment in the original worktree. Do not replace it
with that experiment's weights or the equal-budget parent continuation.
The official champion remains E81. GitHub Actions remains disabled.

## Identity and evidence

All paths below are relative to the checkout unless an absolute path is given.

| Artifact | Path | SHA256 |
|---|---|---|
| Selected weights, epoch 12 | `research/entity_baseline/model.pt` | `cc664b1748ad3f5c704d6fbc471816dcfb59b6a7d7798cef87491468df2fba84` |
| Original Rust descriptor | `research/entity_baseline/model.bin` | `350e96cf53a67f2c07e53c5a3c41c621637733d0a4bd9ef1aa69ee0d0f8fd01b` |
| Frozen corpus registry | `research/entity_baseline/expanded-data.json` | `4dd2f1a9c8f9e78a192a10da1c686dac3481e76c45a4034a931fae61a4eca581` |
| E81 Rust weights | `research/e81/model/model.bin` | `e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8` |

`manifest.json` contains all 12 epoch metrics, selected epoch, script hashes,
and the complete corpus registry. `SHA256SUMS` identifies every frozen file.
The original selected file is also at
`/Users/payton.jones/dev/splendorust/research/architecture_pivots/expanded-entity/model.pt`.
The committed copy has the same bytes, including its checkpoint metadata.

Hypothesis H2: semantic entities and attention improve fit and play relative to
the small model and the deep residual model on matched public data and targets.
The frozen result supports H2 at the tested data scale and fixed search budget.
It does not establish a general architecture limit or an external ranking.

## Architecture and inputs

Definition: `research/architecture_pivots/models.py::EntityTransformer`.
There are **4,780,883 parameters**, width 256, six pre-layer-normalization
Transformer encoder layers, eight attention heads, feed-forward width 1024,
GELU, and zero dropout. A 48-to-256 projection and learned 31-token identity
embeddings precede the layers. The final normalized bank token feeds an
81-logit policy head and a two-value tanh head. No history or auxiliary head
is enabled in this checkpoint.

`entities()` is the token specification; `entities_fast()` is its exact gather
implementation. The 31 tokens each have 48 fields: bank/turn/profile; two
players; 12 market cards; three nobles; six reservations; three deck/pool
tokens; one reservation-context token; and three residual deck-row tokens.
Card cost and bonus rows are combined. Slot identity and public tier fields
remain available. The tokenizer does not impose a board distance.

Inputs are 525 float32 values: 392 deterministic public mean features from the
56-by-7 legacy format, 120 public card-pool membership probabilities, seven
reservation context fields, the native/canonical rules flag at index 519,
and five zero padding fields. Mean features are divided by ten; the turn
field is divided by 124. Context is three blind-slot flags, three public
tier fractions, and a profile-specific marker. The public mean and pool
projection is in `research/e95/public_model.py` and
`research/e86/public_features.py`; Rust uses the matching public projection
at the root and every search leaf. Opponent blind identities and real deck
order are absent. Native action indices use the existing 81-action adapter;
canonical policy/search mappings remain in `transfer.rs` and `neural_search.rs`.

## Corpus and training

Corpus identity: expanded public-525 corpus, engine `splendorust-v2`, upstream
native revision `32a27ac1f85d5de2766cc5f60c2bf04e557f7836`.
There are **1,682,022 training rows from 30,000 disjoint setups**:
1,403,544 native rows / 25,000 games and 278,478 canonical rows / 5,000 games.
Development stays fixed at 111,572 rows / 2,000 separate setups:
55,926 native and 55,646 canonical. No evaluation games are training rows.

Each registry entry gives the absolute source, context, and prepared input
paths and their SHA256s. Locations on this host are:

- Original native: `/Users/payton.jones/dev/splendorust/local/research/e95/{train,dev}/*/data.bin`.
- Original canonical: `local/research/e87/train/004000.bin` and `local/research/e87/dev.bin` under the same root.
- Extra native: `local/research/architecture-pivots/expansion/train/*/data.bin`,
  20,000 AlphaZero800 expert games, master 5110000000.
- Extra canonical: `local/research/architecture-pivots/expansion/canonical/{00,01,02,03}.data.bin`,
  4,000 E81 Gumbel800 expert games, master 5120000000 plus shard times 1000.
- Prepared public tensors: `local/research/architecture-pivots/*.inputs.bin`.

The row dtype is defined in `research/flywheel_model.py::DTYPE`: setup uint64,
392 float32 features, 81-float legal mask, 81-float policy target, float32
teacher value and outcome; 2,232 bytes per row. Context files have seven
float32 fields per row. Inputs files have 525. All file hashes are verified
before training. The targets are one-hot expert actions. The value target is
`2 * ((teacher + outcome) / 2) - 1`; non-finite teacher values use outcome.
Loss is masked policy cross-entropy plus mean squared error against the two
opposite value targets. There are no auxiliary targets in this fit.

The weights were trained from scratch: seed 800000031; 12 full epochs;
batch 512; AdamW, learning rate 0.0003, weight decay 0.0001; cosine decay to
0.00003; gradient norm limit 5; four Torch CPU threads; MPS device;
`--fast-entities`. Shard and row orders use the fixed NumPy seed.
Selection minimizes row-weighted dev policy CE + four times outcome Brier.
Epoch 12 scores 2.222121942: native accuracy 57.5046%, CE 1.253108,
outcome Brier 0.207597; canonical accuracy 48.7349%, CE 1.522819,
outcome Brier 0.209657. MPS training is not guaranteed to reproduce exact
weight bits. The frozen checkpoint is exact. Optimizer state is not saved;
a new `--parent` run starts a new AdamW optimizer and cosine schedule.

## Playing strength and cost

| Scope against E81 | Credit | 95% paired-setup interval | Games | Master / budget |
|---|---:|---:|---:|---|
| Canonical | **60.975%** | 56.7270–65.2230% | 2,000 complete, zero unfinished | 5180000000; both Gumbel128, depth16, pool3; 32 workers |
| Native policy only | **78.275%** | 74.5880–81.9620% | 2,000 complete, zero unfinished | 5190000000; both zero search simulations; 14 workers |

Each 1,000-setup test has both seat rotations. Shared wins receive fractional
credit. Intervals use the registered empirical Bernstein setup-block method.
The canonical records retain width6, strong rollout, engine evaluation,
20,000-decision cap, root-noise zero and Gumbel considered-action cap16.
See the committed `expanded-entity-gate/{run,screen,decision,build}.json`.
Canonical source fingerprint is `cc154030de2934c0`; raw report SHA256 is
`56b568fcde1770f9bf078fdc8091198c03ae278e855c21800b4a63edb2a4d4a5`;
record-set SHA256 is
`ccc994346d4c00693c7820483537257b245834af442db212a6a7b4ff78be2814`.
Native results and replay-checked records are in
`expanded-native-entity-champion/{plan,summary}.json` and `records.json.gz`;
native record-set SHA256 is
`a926502845f07ee747167a92bb50e3f30181350ae80503bcdd88e1785b7fa4d3`.
Native score-cap rules differ from canonical rules; compare these scopes
separately. The native result is not a canonical Gumbel128 result.

Apple M4 Pro, 14 CPU cores, 48 GiB memory, shared host load:
training took 8,990.5 seconds; the canonical test took 1,727.8 seconds;
native took 92.9 seconds. The weights occupy 19,143,225 bytes.
Native policy responses totaled 596.44 seconds for Entity and 8.53 seconds
for E81 across 55,598 decisions each. These are concurrent response costs,
not isolated kernel timings. Tensor-service probes at 1/4/8/14/32 clients
gave 117/526/877/1,325/3,474 calls per second. Occupancy changed no output
bits in that probe. CPU export versus MPS/Rust maximum logit error was
9.537e-6 and maximum masked-policy/value error was 2.235e-6 on 32 real dev
positions. These checks do not prove cross-device trajectory equality.

**Provisional:** both strength results are 2,000-game screens. The decision
file's `promote` means its screen passed; it does not authorize a champion
pointer change. Registered fresh 20,000-game confirmation, broad scaling
cost checks, equal-cost comparisons, and history attribution are pending
in the original study. Only one training seed and two-player play are tested.
**Confirmed within scope:** exact checkpoint identity; complete retained
screen records; matched expanded corpus; held-out fit metrics; checked public
input and bounded numerical parity. No fundamental-bottleneck claim yet.

## Fresh-worktree commands

The weights, source, configuration and screen evidence are committed. Large
expanded corpus files and the Python environment are external local artifacts.
They are not history-experiment state. `bootstrap.py` verifies all 408 corpus
files, writes a worktree-local registry, and attaches only the native dev
directory and runtime. It does not attach history data or experiment outputs.
The default artifact root is `/Users/payton.jones/dev/splendorust`. On another
host, copy the files listed in `expanded-data.json` under the same relative
paths, then use `--data-root PATH --runtime VENV`. Do not delete the original
artifact root while another experiment needs it. Python requirements are
CPython 3.11.13, Torch 2.5.1 and NumPy 1.26.4; MPS is macOS-specific.
Rust is pinned to 1.98.1 with the committed Cargo.lock.
The optional native match also uses the pinned AlphaZero source and Numba;
the default shared runtime already has these dependencies. Canonical
evaluation, model loading and Entity training do not need that upstream.

Run from the root of the new checkout:

```sh
python3 research/entity_baseline/bootstrap.py
local/strength/inference/bin/python research/entity_baseline/check.py
sha256sum -c research/entity_baseline/SHA256SUMS
```

Load directly with `models.load(Path('research/entity_baseline/model.pt'))`
after adding `research/architecture_pivots` to Python's module path.
To export on a separate port, copy the weights into an output directory first;
the exporter writes its descriptor, real-position fixture, and receipt beside
that copy:

```sh
mkdir -p local/research/entity-export
cp research/entity_baseline/model.pt local/research/entity-export/model.pt
local/strength/inference/bin/python research/architecture_pivots/export.py local/research/entity-export/model.pt --port 19546 --slot 13
local/strength/inference/bin/python research/architecture_pivots/service.py --model 13:local/research/entity-export/model.pt --port 19546 --device mps --batch 32 --delay-ms 1 --fast-entities
```

Keep the service running while Rust uses the exported descriptor. Rust does
not link Torch: `transfer/remote.rs` sends only public float tensors to a local
service, checks the exact checkpoint SHA256 at connection, and receives 81
policy logits plus two values. The original descriptor points to port19534,
slot13, history-mode0; it needs the original service. A new port changes the
descriptor hash, not the checkpoint hash. Use a free port for each experiment.

In another terminal, verify export/inference:

```sh
cargo run --release --locked -p splendor-arena --example transfer_parity -- local/research/entity-export/model.bin local/research/entity-export/parity.json real
```

Reproduce the training recipe in a new output directory:

```sh
local/strength/inference/bin/python research/architecture_pivots/train.py --kind entity --data-scale expanded --epochs 12 --batch 512 --device mps --fast-entities --output local/research/entity-retrain
```

For a new experiment from this exact parent, first record its hypothesis and
fixed recipe. Add `--parent research/entity_baseline/model.pt` and use a new
output directory. Parent training uses learning rate 0.0001 by the saved
trainer's rule. Keep the frozen checkpoint and dev split unchanged.

Fresh canonical Gumbel128 evaluation starts its own service, exports a
checkpoint copy, records the configuration, runs the registered gate, and
stops that service. Master5310000000 is reserved for a new baseline screen;
use it once, or register a different disjoint seed before the run:

```sh
local/strength/inference/bin/python research/entity_baseline/evaluate.py --seed 5310000000 --port 19546 --threads 32 --output local/research/entity-fresh-canonical
```

Default screen is 2,000 games with no confirmation. Add `--confirm 20000`
for a registered milestone; its confirmation master is screen master +1e9.
Use CPU only for a separate labeled cost/backend experiment. Retain blocked
and capped games; they reject promotion. The runner checks that
`research/CHAMPION.json` stays byte-identical. No runtime LLM calls, framework
dependencies in Cargo, or history training outputs are needed by this baseline.

Shared public-event and history-capable wire plumbing is committed because
the Rust adapters use those interfaces. Entity history mode remains zero.
The unfinished history trainer, controllers, labels and child checkpoints
are outside this baseline. The original study continues its existing plan.

To run a separate native policy-only check, first attach the pinned engine
with `python3 research/entity_baseline/bootstrap.py --native-upstream`, build
`cargo build --release --locked -p splendor-arena --example strength_worker --example native_policy_worker`,
and start the exported Entity service as above. Then run:

```sh
local/strength/inference/bin/python research/architecture_pivots/native_match.py --model-a local/research/entity-export/model.bin --model-b research/e81/model/model.bin --iterations-a 0 --iterations-b 0 --games 2000 --master 5310100000 --workers 14 --output local/research/entity-fresh-native
```

Use this fresh master once. It does not reuse the original native screen seeds.
