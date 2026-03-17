---
applyTo: "hal/**/*.py,harvest/**/*.py,eval/**/*.py,scripts/**/*.py"
---

# Python — Orion

- All tool calls go through `hal/judge.py` — never bypass the Judge.
- Config values from `hal/config.py` — never hardcode IPs, ports, or paths.
- Use structured logging from `hal/logging_utils.py`, not `print()`.
  (`harvest/`, `eval/`, `scripts/` are exempt — CLI tools may use `print()`.)
- Mypy is strict: annotate all function signatures, no bare `Any`.
- Run `make check` after any change.
