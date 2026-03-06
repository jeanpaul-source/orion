---
applyTo: "ops/**,docker-compose.yml,Dockerfile,Makefile,*.service,*.timer,.env*"
---

# Operations & Infrastructure — Orion Project

When editing deployment, Docker, systemd, or infrastructure files:

## High Risk Zone

These files directly affect the running server. A mistake here can take HAL offline.

- **Always explain what a change will do in plain English before making it.**
- **Always show the rollback command** (how to undo it if it breaks).
- Back up files before overwriting: `cp file file.bak-$(date +%Y%m%d)`.

## Key Constraints (do not change without explicit discussion)

- `OLLAMA_NUM_GPU=0` — prevents VRAM OOM. Removing it crashes vLLM.
- Prometheus is port 9091 (not 9090 — that's Cockpit).
- vLLM needs `VLLM_USE_FLASHINFER_SAMPLER=0` and `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- The server pulls from `main` — broken commits on `main` break the live server.

## Docker

- HAL runs in the `orion` container via Docker Compose.
- Test with `docker compose build` before pushing. Explain Dockerfile directives.

## Systemd

- vLLM, watchdog, and harvest are user systemd units.
- After editing a unit: `systemctl --user daemon-reload && systemctl --user restart <unit>`.
