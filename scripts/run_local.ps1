# One-command local run (Windows PowerShell). Serves UI + API on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r backend\requirements.txt
if ((Get-Command npm -ErrorAction SilentlyContinue) -and -not (Test-Path frontend\dist)) {
  Push-Location frontend; npm install --no-audit --no-fund; npm run build; Pop-Location
}
Write-Host "RECLAIM OS -> http://127.0.0.1:8000  (API docs: /docs)"
Set-Location backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
