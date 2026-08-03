#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  echo "Dependencies are missing; run ./scripts/setup-codex.sh first." >&2
  exit 1
fi

runtime_dir="${NERAIUM_CODEX_RUNTIME_DIR:-$repo_root/.codex-runtime}"
mkdir -p "$runtime_dir"

# Keep cloud development deterministic and offline from AWS. These settings use
# the application's supported local SQLite/filesystem implementations.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
unset NERAIUM_UPLOAD_STATE_BUCKET NERAIUM_AUTH_DATABASE_SECRET_ARN
unset NERAIUM_AUTH_DATABASE_HOST NERAIUM_AUTH_DATABASE_URL
export AWS_EC2_METADATA_DISABLED=true
export APP_ENV=development
export BACKEND_HOST=127.0.0.1
export BACKEND_PORT=8010
export CORS_ORIGINS=http://127.0.0.1:3010,http://localhost:3010
export CORS_ORIGIN_REGEX='^$'
export NERAIUM_RUNTIME_DIR="$runtime_dir"
export NERAIUM_PROCESS_ROLE=monolith
export NERAIUM_START_BACKGROUND_WORKERS=true
export NERAIUM_START_DATA_POLLER=false
export NERAIUM_INFRA_MONITOR_ENABLED=false
export NERAIUM_INLINE_REPLAY_GENERATION=true
export NERAIUM_DEFAULT_TELEMETRY_URL=
export NERAIUM_NOTIFICATION_WEBHOOK_URL=
export NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS=
export NERAIUM_SMTP_HOST=
# Production deployments keep the browser-to-S3 transport default. The local
# Codex preview has no S3 by design, so its production-mode frontend build must
# use the supported direct multipart path instead.
export VITE_PREFER_STORED_UPLOAD=false

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "${backend_pid:-}" ]] && kill "$backend_pid" 2>/dev/null || true
  [[ -n "${frontend_pid:-}" ]] && kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

./.venv/bin/python -m uvicorn app.main:app \
  --app-dir backend --host 127.0.0.1 --port 8010 &
backend_pid=$!

# A production-mode Vite build uses same-origin /api URLs. The checked-in Vite
# preview proxy forwards those requests to the private local backend above, so
# only port 3010 needs to be opened in the Codex port preview.
npm --prefix frontend run build
npm --prefix frontend run preview -- --host 0.0.0.0 --port 3010 &
frontend_pid=$!

echo "Neraium is available on Codex port 3010 (API proxied locally to port 8010)."
wait -n "$backend_pid" "$frontend_pid"
