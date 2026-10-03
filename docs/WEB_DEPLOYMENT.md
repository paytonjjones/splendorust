# SplendoRust web deployment

The web client is a static Vite application in `web/`. React renders the board. A dedicated worker owns the game loop and loads the Rust WebAssembly engine. The production build has no server inference, account service, or runtime model download from a third party.

## Local setup

Use Node.js 22.12 or newer, Python 3, the repository's pinned Rust toolchain, and the `wasm32-unknown-unknown` target. Install JavaScript dependencies from the lockfile:

```sh
cd web
npm ci
```

Install the `wasm-bindgen-cli` version recorded in `Cargo.lock` if it is not available:

```sh
cargo install wasm-bindgen-cli --version 0.2.129 --locked
```

Build and run the site:

```sh
npm run build
npm run dev
```

`npm run build` builds `splendor-web` for `wasm32-unknown-unknown` in release mode with the `external-model-only` feature, runs `wasm-bindgen --target web`, syncs the registered champion into `web/public`, and bundles the result into `web/dist`. This feature excludes bundled research checkpoints; the champion model loads as a separate static asset. The worker imports `web/pkg/splendor_web.js`; Vite follows its WASM URL and emits a content-hashed WASM asset. The CLI must match the `wasm-bindgen` version in `Cargo.lock`.

## Champion replacement

`research/CHAMPION.json` is the source of truth. `npm run sync:champion` verifies its production model SHA-256 and writes:

- `public/champion.json`, fetched at `/champion.json` with no-cache headers;
- `public/models/<sha256>.bin`, served with a one-year immutable cache policy.

If a worktree does not contain the champion metadata and model, the sync script checks `SPLENDORUST_ROOT`, then `/Users/payton.jones/dev/splendorust`. To replace the champion, update the research promotion pointer and model, run the sync script, then build and deploy. Search settings and model hash travel in metadata; the worker should pass those settings through its configuration boundary.

## Cloudflare Pages

The public Pages project is `splendorust`, deployed from `web/dist`. GitHub Actions stays disabled. Deploy locally after reviewing the production assets:

```sh
cd web
npm run build
npm run deploy
```

For the first deployment only, use `npm run deploy -- --create`. With the pinned Wrangler 4.147, the script passes `--force` to project creation so it uses the direct Cloudflare Pages API. The script then deploys the assets. Later deployments use `npm run deploy` without `--force`.

The public site is available at <https://splendorust.pages.dev>.

The deploy script reads `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` from the environment. It can source the established Ring of Binding `.env` by default, or from `$RING_OF_BINDING_ROOT/.env`. It does not need or set `WEBSITE_PASSWORD` because this project is public. Do not print or commit credential values.

## Delivery and performance settings

`public/_headers` enables WASM streaming MIME, same-origin worker loading, cross-origin isolation, a restrictive content security policy with WebAssembly support, immutable caching for Vite assets and the content-addressed model, and no-cache metadata. `public/_redirects` supports the single-page client route. Vite disables asset inlining so WASM remains a separately cacheable file. Model loading is asynchronous in the worker, so the UI can show a loading state while the model downloads.

The `@playwright/test` harness uses a separate `dist-test` build and preview server on port 4174. `VITE_ENABLE_TEST_BRIDGE` is set only in `.env.test`; normal production builds in `dist/` do not expose the test bridge, even when the URL has `?test=1`. `@axe-core/playwright` is available for accessibility specs tagged `@a11y`:

```sh
npm run test:e2e
npm run test:a11y
npm run test:perf
```
