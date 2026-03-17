#!/usr/bin/env bash
# PostToolUse hook: run ruff on Python files immediately after edit.
# Catches lint/format errors right away instead of at commit time.

set -euo pipefail

INPUT=$(cat)

# Only care about file-editing tools
TOOL=$(echo "$INPUT" | jq -r '.toolName // empty')
case "$TOOL" in
  create_file|replace_string_in_file|multi_replace_string_in_file) ;;
  *) exit 0 ;;
esac

# Extract the file path
FILE=$(echo "$INPUT" | jq -r '
  .toolInput.filePath // .toolInput.path // .toolInput.file // empty
')

[ -z "$FILE" ] && exit 0

# Only lint Python files
case "$FILE" in
  *.py) ;;
  *)    exit 0 ;;
esac

# Skip if file doesn't exist (was maybe a failed edit)
[ -f "$FILE" ] || exit 0

# Find ruff — prefer venv, fall back to PATH
RUFF="${RUFF:-}"
if [ -z "$RUFF" ]; then
  for candidate in .venv/bin/ruff venv/bin/ruff; do
    if [ -x "$candidate" ]; then RUFF="$candidate"; break; fi
  done
fi
RUFF="${RUFF:-ruff}"

# Run ruff check (lint) — fast, ~200ms
ERRORS=$("$RUFF" check --no-fix --quiet "$FILE" 2>&1) || true

if [ -n "$ERRORS" ]; then
  jq -n --arg errors "$ERRORS" '{
    systemMessage: ("ruff found issues:\n" + $errors)
  }'
fi
