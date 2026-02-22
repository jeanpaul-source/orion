#!/usr/bin/env bash
# Quick smoke test to ensure core entrypoints run without crashing.

set -euo pipefail

HARVESTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

# Check if orion CLI is installed in venv
if [[ -x "${HARVESTER_DIR}/.venv/bin/orion" ]]; then
  ORION_BIN="${HARVESTER_DIR}/.venv/bin/orion"
else
  echo "❌ orion CLI not found. Install it first:" >&2
  echo "  cd $HARVESTER_DIR && python3 -m venv .venv && source activate.sh && pip install -e ." >&2
  exit 1
fi

echo "🔥 Running smoke tests..."

# 1. Test orion CLI help
echo "  Testing: orion --help"
${ORION_BIN} --help >/dev/null

# 2. Test orion version
echo "  Testing: orion version"
${ORION_BIN} version >/dev/null

# 3. Test providers list
echo "  Testing: orion providers"
${ORION_BIN} providers >/dev/null

# 4. Test validate command
echo "  Testing: orion validate"
${ORION_BIN} validate >/dev/null

# 5. Dry-run harvest to ensure CLI parsing works
echo "  Testing: orion harvest --dry-run"
${ORION_BIN} harvest --term "smoke test" --category gpu-passthrough-and-vgpu --dry-run >/dev/null

echo "✅ Smoke tests completed successfully"
