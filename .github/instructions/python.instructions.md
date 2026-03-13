---
applyTo: "hal/**/*.py,harvest/**/*.py,eval/**/*.py,scripts/**/*.py"
---

# Python — Orion

- All tool calls go through `hal/judge.py` — never bypass the Judge.
- Config values from `hal/config.py` — never hardcode IPs, ports, or paths.
- Use structured logging from `hal/logging_utils.py`, not `print()`.
- Run `make check` after any change.
