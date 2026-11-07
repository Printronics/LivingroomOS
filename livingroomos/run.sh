#!/usr/bin/env bash
# Startet LivingroomOS lokal (nur 127.0.0.1). Schreibt nichts außerhalb des Projektordners,
# außer Browserprofilen unter ~/.local/share/livingroomos, sobald eine Google Chrome-App startet.
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ -f ../.venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source ../.venv/bin/activate
fi
# Use standard asyncio: uvloop does not support the subprocess umask argument required by the process manager.
exec python3 -m uvicorn main:app --loop asyncio --host 127.0.0.1 --port "${LIVINGROOMOS_PORT:-8750}"
