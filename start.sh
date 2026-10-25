#!/usr/bin/env bash
# Starts the Flask backend and the Vite dev server together (macOS/Linux).
# Run ./setup steps from the README once before using this.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "No virtualenv found at .venv. Follow the setup steps in README.md first." >&2
  exit 1
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Frontend packages missing. Run: (cd frontend && npm install)" >&2
  exit 1
fi

(cd "$ROOT/backend" && "$ROOT/.venv/bin/python" run.py) &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null || true' EXIT INT TERM

cd "$ROOT/frontend" && npm run dev
