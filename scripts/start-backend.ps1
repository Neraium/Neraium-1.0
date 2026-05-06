$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendPath = Join-Path $RepoRoot "backend"

Set-Location $BackendPath

if (-not $env:BACKEND_HOST) {
    $env:BACKEND_HOST = "127.0.0.1"
}

if (-not $env:BACKEND_PORT) {
    $env:BACKEND_PORT = "8010"
}

python -m uvicorn app.main:app --reload --host $env:BACKEND_HOST --port $env:BACKEND_PORT
