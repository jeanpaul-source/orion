---
applyTo: "hal/static/**"
---

# Web UI — Orion

- Vanilla JS — no frameworks, no build step, no npm.
- Served by FastAPI at `GET /` from `hal/static/`.
- Markdown: `marked.js` (CDN), syntax highlighting: `highlight.js` (CDN).
- Dark theme only — no light theme toggle exists.
- Backend changes may also be needed in `hal/server.py`.
