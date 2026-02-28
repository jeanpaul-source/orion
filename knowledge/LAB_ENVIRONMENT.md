# Lab Environment — Ground Truth

This document is the authoritative description of the homelab. HAL uses this
as highest-priority context when answering questions about YOUR setup.
Keep it updated when things change.

---

## Host: the-lab (192.168.5.10)

**OS:** Fedora Linux 43 (Server Edition)

**Hardware:**

- **CPU:** Intel Core Ultra 7 265K (20 cores)
- **RAM:** 62 GB DDR5
- **GPU:** NVIDIA RTX 3090 Ti (24 GB VRAM)
- **Storage:**
  - Samsung 990 PRO 2TB — boot/root
  - 2x WD SN850X 2TB — /docker, /data/projects
- **Tailscale:** 100.82.66.91

**Services running:**

| Service | Port | Type | Notes |
|---|---|---|---|
| Ollama | 11434 | systemd (bare metal) | CPU-only (OLLAMA_NUM_GPU=0), embeddings |
| vLLM | 8000 | user systemd | Qwen2.5-32B-Instruct-AWQ, full GPU |
| pgvector-kb | 5432 | Docker | PostgreSQL+pgvector, DB: knowledge_base |
| pgvector-kb-api | 5001 | systemd | search API |
| Prometheus | 9091 | Docker | host port 9091 (Cockpit is 9090) |
| Grafana | 3001 | Docker | |
| Pushgateway | 9092 | Docker | HAL metrics |
| ntopng | 3000 | Docker | interface enp130s0 |
| Falco | - | system systemd | eBPF modern-bpf |
| Osquery | - | bare metal | 5.21.0 |
| HAL HTTP server | 8087 | user systemd | FastAPI, server.service |
| HAL Telegram bot | - | user systemd | telegram.service |
| Watchdog | - | user systemd timer | 30min interval |
| Harvest | - | user systemd timer | 3:00am daily |

---

## Dev Machine: Laptop (192.168.5.25)

- **OS:** Ubuntu desktop
- **Repo:** /home/jp/orion
- **Role:** edit code, push to GitHub; server pulls only

---

## Network

<!-- FILL THESE IN — this is what HAL needs to plan network projects -->

- **Router model:** (describe)
- **Switch model:** (describe)
- **LAN subnet:** 192.168.5.0/24
- **VLANs:** (describe if any)
- **DNS:** (describe — Pi-hole? router? ISP?)
- **ISP:** (describe — speed, type, static IP?)
- **Other devices on the network:** (list anything HAL should know about)
- **Firewall:** (describe current setup or "none")

---

## Secrets Management

- SOPS + `homelab-secrets.service` on the-lab
- tmpfs at `/run/homelab-secrets/`
- `.env` files are gitignored; synced via `scp` from laptop to server
- Never edit `.env` directly on the server

---

## Goals and Constraints

<!-- FILL THESE IN — tells HAL what you're trying to achieve -->

- What should HAL be able to do? (describe)
- What should HAL NOT do? (describe restrictions)
- Budget or hardware constraints? (describe)
- Future plans? (backup server, firewall box, etc.)
