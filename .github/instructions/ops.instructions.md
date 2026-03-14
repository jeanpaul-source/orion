---
applyTo: "ops/**,docker-compose.yml,Dockerfile,Makefile,*.service,*.timer,.env*"
---

# Operations — Orion

These files directly affect the running server. A mistake here takes HAL offline.

## Before any change

- Explain what the change does in plain English.
- Show the rollback command.

## Load-bearing constraints

- `OLLAMA_NUM_GPU=0` — prevents VRAM OOM. See OPERATIONS.md.
- Prometheus is port 9091, not 9090 (that's Cockpit).
- vLLM needs `VLLM_USE_FLASHINFER_SAMPLER=0` and `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- After systemd unit edits: `systemctl --user daemon-reload && systemctl --user restart <unit>`.
