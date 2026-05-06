$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendPath = Join-Path $RepoRoot "backend"

Set-Location $BackendPath
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
