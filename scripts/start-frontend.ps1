$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendPath = Join-Path $RepoRoot "frontend"

Set-Location $FrontendPath
$env:VITE_API_BASE_URL = "http://127.0.0.1:8010"
npm run dev
