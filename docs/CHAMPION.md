# Champion weights

The strength champion is `entity-onehot-generation-one-puct6400`. Its
4,780,883-parameter Entity Transformer weights are public under the
[MIT license](../LICENSE). You can use, modify, and redistribute them under
that license.

## Download

| File | Use | Size after decompression |
| --- | --- | ---: |
| [Rust/WASM model](https://raw.githubusercontent.com/paytonjjones/splendorust/main/web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin) | Local Rust or browser inference. The file contains the weights, not a service connection. | 19,123,540 bytes |
| [PyTorch checkpoint, gzip](https://raw.githubusercontent.com/paytonjjones/splendorust/main/research/training_strategy/artifacts/core/chunks/first/onehot/runtime.pt/0000.gz) | Load the saved model for research or export. Decompress this file to `champion.pt`. | 19,148,003 bytes |

The files are also in a repository checkout. Restore the checkpoint without
installing Python packages:

```sh
gzip -dc research/training_strategy/artifacts/core/chunks/first/onehot/runtime.pt/0000.gz > champion.pt
shasum -a 256 champion.pt
shasum -a 256 web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin
```

The expected SHA-256 values are:

```text
PyTorch checkpoint:
ef8a4521cd6c03c7075f15efee23f4cde6ec94d1b5398765cf0c24a09ad745cb

Rust/WASM model:
57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb
```

The [champion record](../research/STRENGTH_CHAMPION.json) binds these hashes to
its search settings and confirmed result. The
[archive manifest](../research/training_strategy/artifacts/core/manifest.json)
records the compressed checkpoint hash too.

## Run the model

For browser play or a local browser build, use
[the web setup guide](WEB_DEPLOYMENT.md). The build selects the strength
champion, checks its model hash, and loads its weights in Rust/WASM. It does
not need a remote model service. A deployed site's footer identifies the model
loaded by that deployment.

For PyTorch, use [the architecture and loader](../research/architecture_pivots/models.py).
The [export tool](../research/architecture_pivots/export.py) supports
`--native-entity` to produce the Rust/WASM format. Other research exports can
produce a service descriptor; that small descriptor is not a weight file.

For the confirmed native benchmark's tensor service, search settings, evidence,
and restoration, use [the campaign runbook](../research/sprint48/README.md) and
[delivery record](../research/sprint48/FINAL_DELIVERY.md). The campaign is complete;
old test seeds are used evidence, not fresh evaluation data.

## What was measured

These weights with PUCT6400 earned 77.5% win credit in 1,000 complete native
AlphaZero games against unchanged AlphaZero800. The conservative 95% interval
was 71.43–83.57%. The candidate used more search compute. This result does not
establish the same strength in browser games, under canonical rules, at equal
compute, or against expert humans. See [the full result](../research/sprint48/RESULTS.md).
