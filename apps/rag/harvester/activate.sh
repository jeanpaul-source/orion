#!/bin/bash
# ORION venv activation helper
# Usage: source activate.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${SCRIPT_DIR}/.venv"

if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at: $VENV_PATH"
    echo "Run: python3 -m venv .venv && pip install -e ."
    return 1
fi

# Deactivate any current venv
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate 2>/dev/null || true
fi

# Activate correct venv
source "$VENV_PATH/bin/activate"

# Verify orion is available
if command -v orion &> /dev/null; then
    echo "✅ ORION venv activated: $VENV_PATH"
    echo "   orion: $(which orion)"
    orion --version
else
    echo "⚠️  orion command not found. Install with: pip install -e ."
fi
