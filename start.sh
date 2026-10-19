#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  [[ -z "$FRONTEND_PID" ]] || kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -z "$BACKEND_PID" ]] || kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if ! command -v python >/dev/null 2>&1; then echo "Erro: Python não encontrado." >&2; exit 1; fi
if ! command -v npm >/dev/null 2>&1; then echo "Erro: Node.js/npm não encontrado." >&2; exit 1; fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Dependências do frontend ausentes. Execute: cd frontend && npm install" >&2
  exit 2
fi

(
  cd "$ROOT/backend"
  export APP_HOST=0.0.0.0 APP_PORT=8000
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!
(
  cd "$ROOT/frontend"
  exec npm run dev -- --host 0.0.0.0
) &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000"
echo "Health:   http://localhost:8000/api/health"
echo "Swagger:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
wait -n "$BACKEND_PID" "$FRONTEND_PID"
