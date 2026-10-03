#!/usr/bin/env bash
set -euo pipefail

web_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$web_dir/.." && pwd)"
crate="splendor-web"
target="wasm32-unknown-unknown"
out_dir="$web_dir/pkg"

if ! cargo metadata --no-deps --format-version 1 --manifest-path "$repo_dir/Cargo.toml" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if any(p["name"] == "splendor-web" for p in d["packages"]) else 1)'; then
  echo "Rust crate splendor-web is not present in the workspace yet." >&2
  exit 1
fi

locked_bindgen_version="$(python3 - "$repo_dir/Cargo.lock" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as f:
    lock = tomllib.load(f)
versions = sorted({p["version"] for p in lock["package"] if p["name"] == "wasm-bindgen"})
if len(versions) != 1:
    raise SystemExit(f"Expected one locked wasm-bindgen version, found: {versions}")
print(versions[0])
PY
)"

if ! rustup target list --installed | grep -Fxq "$target"; then
  rustup target add "$target"
fi

if ! command -v wasm-bindgen >/dev/null 2>&1; then
  echo "wasm-bindgen CLI is required. Install the Cargo.lock version with:" >&2
  echo "  cargo install wasm-bindgen-cli --version $locked_bindgen_version --locked" >&2
  exit 1
fi

cli_version="$(wasm-bindgen --version | awk '{print $2}')"
if [[ "$cli_version" != "$locked_bindgen_version" ]]; then
  echo "wasm-bindgen CLI $cli_version does not match Cargo.lock version $locked_bindgen_version." >&2
  echo "Install the locked version with: cargo install wasm-bindgen-cli --version $locked_bindgen_version --locked" >&2
  exit 1
fi

cargo build --manifest-path "$repo_dir/Cargo.toml" -p "$crate" --features external-model-only --target "$target" --release --locked
rm -rf "$out_dir"
wasm-bindgen \
  "$repo_dir/target/$target/release/splendor_web.wasm" \
  --target web \
  --out-dir "$out_dir" \
  --out-name splendor_web
