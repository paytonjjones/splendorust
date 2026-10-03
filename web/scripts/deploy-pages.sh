#!/usr/bin/env bash
set -euo pipefail

web_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$web_dir/.." && pwd)"
ring_root="${RING_OF_BINDING_ROOT:-/Users/payton.jones/dev/ring_of_binding}"

if [[ ( -z "${CLOUDFLARE_ACCOUNT_ID:-}" || -z "${CLOUDFLARE_API_TOKEN:-}" ) && -f "$ring_root/.env" ]]; then
  set -a
  # The Ring deployment uses these same credential names. Values stay out of output.
  # shellcheck disable=SC1091
  source "$ring_root/.env"
  set +a
fi

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID or provide it in $ring_root/.env}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN or provide it in $ring_root/.env}"

export CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN

if [[ ! -d "$web_dir/dist" ]]; then
  echo "Production build is missing. Run npm run build first." >&2
  exit 1
fi

cd "$web_dir"
if [[ "${1:-}" == "--create" ]]; then
  # Wrangler 4.147 delegates Pages commands unless forced to use the direct Pages API.
  ./node_modules/.bin/wrangler pages project create splendorust --production-branch=main --force
fi
./node_modules/.bin/wrangler pages deploy dist --project-name=splendorust --branch=main
