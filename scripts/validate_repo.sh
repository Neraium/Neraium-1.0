#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -n "${PYTEST_BIN:-}" ]]; then
  pytest_bin="$PYTEST_BIN"
elif [[ -x ./.venv/bin/pytest ]]; then
  pytest_bin="./.venv/bin/pytest"
elif [[ -x ./backend/.venv/bin/pytest ]]; then
  pytest_bin="./backend/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  pytest_bin="pytest"
else
  echo "pytest executable not found. Set PYTEST_BIN or create .venv/backend/.venv." >&2
  exit 127
fi
"$pytest_bin" -q
npm --prefix frontend run lint:ci
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- --project=chromium tests/e2e/smoke.spec.js
