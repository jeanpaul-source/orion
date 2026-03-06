---
applyTo: "hal/static/**,**/*.html,**/*.css,**/*.js"
---

# Web UI — Orion Project

When editing the Web UI files (HTML, CSS, JavaScript):

## Architecture

- The Web UI is served by FastAPI at `GET /` from `hal/static/`.
- Vanilla JS — no frameworks, no build step, no npm.
- Markdown rendered by `marked.js` (CDN), syntax highlighting by `highlight.js` (CDN).
- Sessions stored in browser `localStorage`.

## Style

- Dark theme, monospace-rooted design. Maintain visual consistency.
- Mobile-responsive — test that sidebar collapses properly.
- Explain CSS concepts (flexbox, grid, media queries, z-index) when introducing them.

## Safety

- Changes to `hal/server.py` (the backend) affect the web UI. Explain the connection.
- Test changes by checking `curl http://localhost:8087/` or opening the browser.
