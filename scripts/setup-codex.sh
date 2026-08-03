#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python3.11}"
python_command=("$python_bin")
if ! "$python_bin" --version >/dev/null 2>&1; then
  pyenv_python="$(command -v pyenv >/dev/null 2>&1 && pyenv versions --bare | sed -n '/^3\.11\./p' | tail -1 || true)"
  if [[ -z "$pyenv_python" ]]; then
    echo "Python 3.11 is required (override its executable with PYTHON_BIN)." >&2
    exit 1
  fi
  python_command=(env "PYENV_VERSION=$pyenv_python" python)
fi

if [[ -x .venv/bin/python ]] && [[ "$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.11" ]]; then
  rm -rf .venv
fi
"${python_command[@]}" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci

echo "Codex dependencies are installed. Run ./scripts/run-codex.sh to start Neraium."
