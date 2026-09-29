# Two-player policy block evidence

The four blocked histories remain nonterminal with no winner. The new policies
complete all four recorded games. Only agents change; core remains version 2.

- E19 blocks 786/rotation 1 and 6349/rotation 0 affect Strong identity 1.
- E20 extends own-turn safety to real Strong decisions and token returns.
  Its fresh 138m/1,138m gate rejects two new blocked confirmation games.
- E21 also avoids a take that proves the next actor has no legal action.
  Unknown blind reservations prevent that proof. An active final-round finish
  and a mandatory return are not rejected by this check.
- Search's internal rollouts keep their existing heuristic scoring.

`../../e20-policy.patch` reproduces the failed E20 agent
source on commit 3502da4. Its reconstructed production fingerprint is
`e8aca47ca9f7bf5b`. The final E21 fingerprint is `bc768d0c493a603f` on this
worktree's production files. Benchmark feature changes in another branch
can produce a different fingerprint even with the same agent decisions.

The compressed reports are exact raw arena output. Adjacent summaries have
independently recomputed setup-block intervals and record-set hashes. The
local index includes these reports without changing the global historical
index. Manifests, gate decisions, binary hashes, failed gate execution, and
full gate logs remain beside them. Promotion runtime is shared-machine
metadata, not a comparative performance result.

Reproduce the targeted checks:

```sh
cargo test --release --locked -p splendor-arena --test search_safety
cargo run --release --locked --example two_block_audit -- \
  crates/splendor-arena/tests/fixtures/blocked-two-786-v2.json 1 \
  crates/splendor-arena/tests/fixtures/blocked-two-6349-v2.json 0
```

Reproduce the gates in new output directories, with the exact final source:

```sh
python3 scripts/promote.py --candidate search --baseline strong --players 2 \
  --screen 2000 --confirm 20000 --seed 140000000 --threads 4 --iterations 128 \
  --output results/e21-reproduce/two
python3 scripts/promote.py --candidate search --baseline strong --players 3 \
  --screen 3000 --confirm 21000 --seed 141000000 --threads 4 --iterations 128 \
  --output results/e21-reproduce/three
python3 scripts/promote.py --candidate search --baseline strong --players 4 \
  --screen 4000 --confirm 20000 --seed 142000000 --threads 4 --iterations 128 \
  --output results/e21-reproduce/four
```

These reproduction seeds are not fresh holdouts for later policy changes.
The strength result is conditional on the changed Strong opponents and
128 simulations/depth 8/width 6. It does not isolate a strength benefit from
either safety change. No tested finite set proves universal termination.

A separate invariant-checked Search32 self-play diagnostic at master seed
143m has these results. It is retained as an incomplete reference:

| Players | Requested | Complete | Blocked | Capped |
|---|---:|---:|---:|---:|
| 2 | 300 | 293 | 0 | 7 |
| 3 | 300 | 298 | 2 | 0 |
| 4 | 300 | 298 | 2 | 0 |

All seven caps have a verified four-decision token-only cycle. Three-player
blocks concern a blind opponent reservation or a free purchase outside the
take-only guard. Four-player blocks have only one legal final take. The
reports, all eleven histories, and audits preserve these unfinished games
without a winner. These bounded checks establish no E21 guard defect.
