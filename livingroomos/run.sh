#!/usr/bin/env bash
# Starts LivingroomOS locally (127.0.0.1 only). Writes nothing outside the project directory,
# except for browser profiles under ~/.local/share/livingroomos when a Google Chrome app starts.
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ -f ../.venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source ../.venv/bin/activate
fi
# Use standard asyncio: uvloop does not support the subprocess umask argument required by the process manager.
exec python3 -m uvicorn main:app --loop asyncio --host 127.0.0.1 --port "${LIVINGROOMOS_PORT:-8750}"
