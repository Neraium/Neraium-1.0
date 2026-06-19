#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

./.venv/bin/pytest -q
npm --prefix frontend run lint:ci
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- --project=chromium tests/e2e/smoke.spec.js
