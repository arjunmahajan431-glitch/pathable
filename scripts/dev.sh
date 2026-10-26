#!/usr/bin/env bash
# Run the FastAPI backend and Vite frontend together.
#
#   ./scripts/dev.sh                 # use a cached graph, or the labeled demo graph
#   PATHABLE_DEMO=1 ./scripts/dev.sh # force the committed demo extract
#
# The backend loads once at startup. If the graph is missing the API serves the
# labeled sample extract, which is useful for a demo but is never presented as
# live data.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

if [[ ! -x backend/.venv/bin/uvicorn ]]; then
  echo "Backend environment missing. Run: make setup" >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "Frontend dependencies missing. Run: make setup" >&2
  exit 1
fi

kill_tree() {
  local pid="$1"
  local signal="${2:-TERM}"
  local child
  # Uvicorn's reloader and npm both spawn children; killing only the parent
  # can leave a server listening after Ctrl-C.
  for child in $(ps -o pid= --ppid "$pid" 2>/dev/null || true); do
    kill_tree "$child" "$signal"
  done
  kill -"$signal" "$pid" 2>/dev/null || true
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  [[ -n "${backend_pid:-}" ]] && kill_tree "$backend_pid" TERM
  [[ -n "${frontend_pid:-}" ]] && kill_tree "$frontend_pid" TERM
  sleep 1
  [[ -n "${backend_pid:-}" ]] && kill_tree "$backend_pid" KILL
  [[ -n "${frontend_pid:-}" ]] && kill_tree "$frontend_pid" KILL
  wait 2>/dev/null || true
  exit "$code"
}
trap cleanup EXIT INT TERM

(
  cd backend
  exec .venv/bin/uvicorn pathable.api.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) &
backend_pid=$!

(
  cd frontend
  exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT"
) &
frontend_pid=$!

echo "API:      http://127.0.0.1:${BACKEND_PORT}/api/docs"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "Press Ctrl-C to stop both."

wait
