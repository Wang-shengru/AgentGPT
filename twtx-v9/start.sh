#!/usr/bin/env bash
# TWTX V9 一鍵啟動（macOS / Linux）
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { cp .env.example .env; echo "已建立 .env（預設 Mock 模式）"; }
set -a; . ./.env; set +a

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
. .venv/bin/activate
REQ=backend/requirements.txt
if [ -n "${SJ_API_KEY:-}" ] && [ "${TWTX_MODE:-}" != "mock" ]; then REQ=backend/requirements-live.txt; fi
pip install -q -r "$REQ"

if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src -newer frontend/dist/index.html -print -quit 2>/dev/null)" ]; then
  command -v npm >/dev/null || { echo "需要 Node.js 18+ 以建置前端"; exit 1; }
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

echo "開啟 http://${BIND_HOST:-127.0.0.1}:${API_PORT:-8001}"
cd backend && exec python -m twtx
