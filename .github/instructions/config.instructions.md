---
applyTo: "hal/config.py,.env*"
---

# Config — Orion

- `hal/config.py` is the single source of truth for all runtime values.
- Every `os.getenv()` call in config.py must have a matching entry in `.env.example`.
- After changing config.py, run `make doc-drift` — it verifies env vars are documented.
- Never add a new port, host, or path as a literal anywhere else. Add it to config.py.
