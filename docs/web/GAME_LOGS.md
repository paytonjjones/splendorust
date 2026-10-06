# Visitor game records

The production site records all visitor games. The browser keeps a durable IndexedDB copy and uploads full action prefixes to private Cloudflare D1 storage. Search does not wait for storage or network requests. Failed uploads retry. Closing a tab sends the latest small record with `keepalive`; records that remain pending retry when the browser returns. Browser storage removal or a tab close before a durable write can lose a pending record.

The site has no accounts. Each game has a random ID and a separate random write token. The database stores only the token hash. The public endpoint accepts writes and provides no game reads. The application does not collect names, email addresses, IP addresses, or a persistent visitor ID. The help panel tells players that moves are collected for training research.

## Record format

Each JSONL line has schema `splendor-web-game-v1`. It includes the human seat, champion metadata, model hash, effective search settings, runtime, client timestamps, version, status, and a Rust replay. The replay uses `splendor-web-replay-v1`, with the engine version, exact decimal-string u64 seed, every successful canonical seven-byte action, revision, turns, exact diagnostic state, and result. It includes forced payments, returns, nobles, and bot decisions. Failed actions do not change the journal.

The game status is `in_progress`, `finished`, `blocked`, `abandoned`, or `error`. Keep every status. Unfinished and blocked games have no invented winner. Test builds are marked `test` and do not upload by default. They need both `VITE_GAME_LOG_TEST_UPLOAD=true` and `?test=1&uploadLogs=1` for an explicit integration check.

The endpoint limits a record to 512 KiB, 8,192 decisions, and 256 KiB of diagnostic state. A rejected upload leaves the local copy available for download. These limits are far above the tested complete games; they bound untrusted requests.

## Export

Players can use **Download your games** for a JSONL copy from their browser. It excludes write tokens and upload bookkeeping.

For all visitor records, run from `web/`:

```sh
npm run logs:export -- --out ../local/web-games/visitor-games.jsonl
```

This uses the existing Wrangler OAuth login in the established Cloudflare account. The Ring Pages API token does not have D1 access, so the exporter removes it from its child process environment. No new credential or permission is required. If the existing login expires, use the usual Wrangler login flow.

The exporter reads 100 rows per page, checks each stored snapshot hash, and writes a private JSONL file plus a SHA-256 manifest with status, runtime, engine, and model counts. It refuses to overwrite an existing export. Production games are included by default. Add `--include-test` to inspect integration fixtures, or `--local` to inspect the local D1 database. Concurrent game updates can occur while pages are read; the output hash identifies the exact exported record set.

## Validate before training

From the repository root:

```sh
cargo run --release --locked -p splendor-arena --example validate_web_records -- local/web-games/visitor-games.jsonl
```

The validator replays the exact actions through the Rust engine, checks invariants, and compares state, turns, revision, and result. It returns a failure if any record is rejected and reports finished, blocked, and each nonterminal status separately. Use the engine version that matches the records.

The WebGPU client adds `inferenceBackend: "webgpu-f32"` and `turnBudgetMs: 10000` to effective search settings. The simulation setting is a ceiling under this time cap. Older CPU records remain valid. Do not treat capped browser records as fixed-budget native champion games.

Client records are untrusted. Legal replay does not prove a human identity or authenticate champion metadata. Reconstruct each acting player's `Observation` for learner inputs. Keep the seed and full diagnostic state for validation; do not feed hidden deck order or an opponent's private reservations to a public-input learner. Collecting records does not automatically train or promote a model.

## Storage setup

`web/wrangler.jsonc` binds `GAME_LOGS` to private D1 database `splendorust-game-logs`. Apply the checked-in migration with the existing OAuth session:

```sh
env -u CLOUDFLARE_API_TOKEN npx wrangler d1 migrations apply splendorust-game-logs --remote
```

Only `/api/*` invokes Pages Functions. Static game assets keep their normal cache path. Database failures leave the game playable and preserve local records for retry or download.
