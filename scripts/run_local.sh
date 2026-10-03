#!/usr/bin/env bash
# One-command local run (macOS/Linux). Builds the UI if Node is available, then serves everything on :8000.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r backend/requirements.txt
if command -v npm >/dev/null 2>&1 && [ ! -d frontend/dist ]; then (cd frontend && npm install --no-audit --no-fund && npm run build); fi
echo "RECLAIM OS → http://127.0.0.1:8000   (API docs: /docs)"
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
