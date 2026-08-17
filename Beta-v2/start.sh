#!/usr/bin/env bash
# Bash startup wrapper for the verified Beta-v2 launcher.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    BETA_PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
    BETA_PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"
else
    echo "[ERROR] Beta-v2 virtual environment is missing. Follow README.md first-time setup." >&2
    exit 1
fi

exec "$BETA_PYTHON" "$SCRIPT_DIR/run.py"
