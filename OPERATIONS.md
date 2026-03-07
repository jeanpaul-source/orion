# Operations

Deploy, configure, and run Orion/HAL on the homelab server.

---

## Prerequisites

**On the server (`the-lab`, `192.168.5.10`):**

- Docker + Docker Compose v2
- Python 3.12+ venv (for harvest and watchdog — host-only tools)
- SSH key-based access to `LAB_HOST` (no password prompt on connect)

| Service | How it runs | Port | Notes |
| --- | --- | --- | --- |
| **HAL** | Docker Compose (`orion` container) | 0.0.0.0:8087 | HTTP server + Web UI + Telegram bot via supervisord. Open `http://<server-ip>:8087` in a browser for the Web UI. Requires `HAL_WEB_TOKEN` for `/chat`. |
| vLLM | user systemd `vllm.service` | 8000 | Chat LLM — must be fully loaded before starting HAL |
| Ollama | system systemd | 11434 | Embeddings only, CPU-bound — `OLLAMA_NUM_GPU=0` is load-bearing |
| pgvector | Docker | 5432 | PostgreSQL + pgvector extension |
| Prometheus | Docker | 9091 | **Not 9090** — port 9090 is Cockpit |
| Grafana | Docker | 3001 | |
| Pushgateway | Docker | 9092 | HAL metrics target |
| Grafana Tempo | Docker | 4318 / 3200 | OTel trace receiver (OTLP HTTP) + query API; monitoring-stack compose |
| Falco | system systemd | — | `falco-modern-bpf.service`; JSON events at `/var/log/falco/events.json` |
| Osquery | bare metal | — | Version 5.21.0; `/etc/sudoers.d/osquery-hal` scoped to `osqueryi` only |
| ntopng | Docker Compose | 3000 | `~/ntopng/docker-compose.yml`; login disabled; Community API at `/lua/rest/v2/` |
| Nmap | bare metal | — | Version 7.92 |

---

## Setup

```bash
git clone https://github.com/jeanpaul-source/orion
cd orion
cp .env.example .env
```

Fill in `PGVECTOR_DSN` password from the server:

```bash
cat /run/homelab-secrets/pgvector-kb.env
```

Build and start the container:

```bash
docker compose build
docker compose up -d
```

The server takes ~30 seconds to connect to external services (vLLM, pgvector,
Ollama). Watch logs with `docker logs -f orion`.

For harvest and watchdog (host-only tools that need direct system access), set
up the host venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m harvest     # initial KB population
```

---

## `.env` reference

All variables have defaults in `config.py`. Server `.env` uses `localhost`. Laptop `.env`
uses the server IP and `USE_SSH_TUNNEL=true`.

| Variable | Default | Notes |
| --- | --- | --- |
| `VLLM_URL` | `http://localhost:8000` | vLLM OpenAI-compatible API — `localhost` on server, tunneled on laptop |
| `CHAT_MODEL` | `Qwen/Qwen2.5-32B-Instruct-AWQ` | Must exactly match the model loaded in vLLM |
| `OLLAMA_HOST` | `http://192.168.5.10:11434` | Embeddings only — do not point at vLLM |
| `EMBED_MODEL` | `nomic-embed-text:latest` | Must be pulled in Ollama (`ollama pull nomic-embed-text`) |
| `PGVECTOR_DSN` | `postgresql://kb_user@192.168.5.10:5432/knowledge_base` | **Fill in the password** |
| `PROMETHEUS_URL` | `http://192.168.5.10:9091` | Port **9091** — 9090 is Cockpit |
| `NTOPNG_URL` | `http://localhost:3000` | ntopng REST API — no auth (login disabled, local only) |
| `LAB_HOST` | `192.168.5.10` | SSH target for remote commands |
| `LAB_USER` | `jp` | SSH user on the server |
| `EXTRA_HOSTS` | *(empty)* | Additional SSH hosts — comma-separated `name:user@ip` entries (e.g. `laptop:jp@192.168.5.20`). Each host must have SSH key-based access from the HAL server. |
| `USE_SSH_TUNNEL` | `false` | Set `true` when running from a laptop |
| `NTFY_URL` | *(empty)* | Push alerts via ntfy.sh topic URL — leave empty to disable |
| `HAL_INSTANCE` | *(hostname)* | Grafana Pushgateway label — set `laptop` or `the-lab` explicitly |
| `PROM_PUSHGATEWAY` | *(empty)* | `http://localhost:9092` (server) or `http://192.168.5.10:9092` (laptop) |
| `HAL_LOG_JSON` | `1` | `1` = JSON logs, `0` = plain text |
| `HAL_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OTLP_ENDPOINT` | `http://localhost:4318` | OTel OTLP HTTP — no-op if unreachable |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | From @BotFather — leave empty to disable bot |
| `TELEGRAM_ALLOWED_USER_ID` | `0` | Numeric Telegram user ID — get from @userinfobot |
| `HAL_WEB_TOKEN` | *(empty)* | Bearer token for `/chat` — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. **Required** when port is LAN-exposed. |

---

## Running HAL

HAL runs inside the `orion` Docker container. The REPL, HTTP server, and
Telegram bot all run inside the container.

```bash
# Interactive REPL (attaches to running container)
hal     # alias: docker exec -it orion python -m hal

# Start fresh session
docker exec -it orion python -m hal --new

# Container management
docker compose up -d      # start
docker compose down       # stop
docker logs -f orion      # follow logs
docker compose restart    # restart
```

HAL's state lives at `~/.orion/` on the host, mounted as `/home/hal/.orion`
inside the container. Session DB at `~/.orion/memory.db`, readline history
at `~/.orion/history`, audit log at `~/.orion/audit.log`.

---

## Systemd units

HAL itself runs in Docker Compose (not systemd). The old `server.service` and
`telegram.service` are **disabled** — kept as rollback path only.

The following units are still active as **user systemd** on the host:

### Deploy a unit

```bash
cp ops/<unit>.service ~/.config/systemd/user/
cp ops/<unit>.timer   ~/.config/systemd/user/     # if applicable
systemctl --user daemon-reload
systemctl --user enable --now <unit>.timer
```

### vLLM (`ops/vllm.service`)

The chat LLM. Serves Qwen2.5-32B-Instruct-AWQ on port 8000 via vLLM.

```bash
systemctl --user status vllm.service
systemctl --user restart vllm.service
journalctl --user -u vllm -f
```

**Load-bearing environment variables** in the unit file — do not remove:

- `VLLM_USE_FLASHINFER_SAMPLER=0` — fixes CUDA device-side assert crash on RTX 3090 Ti
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` — prevents KV cache OOM under load

vLLM takes 60–90 seconds to load the model. HAL's `ping()` checks the `/health` endpoint
which returns 200 only when the model is fully loaded (not on API server start).

To update the unit file:

```bash
cp ops/vllm.service ~/.config/systemd/user/vllm.service
systemctl --user daemon-reload && systemctl --user restart vllm.service
```

### Watchdog (`ops/watchdog.service` + `ops/watchdog.timer`)

Standalone health monitor. Fires every 5 minutes via timer. Checks service health and
resource state. Alerts via ntfy when `NTFY_URL` is set; logs always.

```bash
systemctl --user status watchdog.timer
systemctl --user restart watchdog.service   # run immediately
journalctl --user -u watchdog -f
```

State file: `~/.orion/watchdog_state.json` — tracks per-metric cooldowns.

### Harvest (`ops/harvest.service` + `ops/harvest.timer`)

Re-indexes the lab into pgvector. Fires at 3:00am daily (`Persistent=true` — catches up
on missed runs after downtime).

```bash
systemctl --user status harvest.timer
systemctl --user list-timers harvest.timer
python -m harvest              # manual run
python -m harvest --dry-run   # preview only
```

### Knowledge base tiers

The harvest pipeline populates a three-layer knowledge base via the `doc_tier` column:

| Tier | Source | Harvest behavior |
| --- | --- | --- |
| `ground-truth` | `knowledge/*.md` in the repo | Cleared and re-ingested every run |
| `reference` | `/data/orion/orion-data/documents/raw` (HTML, PDF, text) | Incremental — unchanged docs skipped via content hash; orphan rows cleaned |
| `live-state` | Docker, systemd, disk, memory, ports, hardware, configs | Cleared and re-ingested every run |
| `memory` | `/remember` facts | Never touched by harvest |

Ground-truth docs get a +0.10 score boost in KB search results.

### Syncing the reference library (laptop to server)

The 2.3 GB reference library lives on the laptop and is **not** in git. Sync via rsync:

```bash
rsync -av --delete \
  /home/jp/Laptop-MAIN/applications/orion-harvester/data/library/ \
  jp@192.168.5.10:/data/orion/orion-data/documents/raw/
```

After syncing, run `python -m harvest` on the server (or wait for the nightly timer).
The `--delete` flag + orphan cleanup ensures removed files don't leave stale KB rows.

### HAL container (Docker Compose)

The HTTP server and Telegram bot run inside the `orion` container via
supervisord (`ops/supervisord.conf`). Both auto-restart on failure.

```bash
# Deploy / update
orion-deploy    # alias: cd ~/orion && git pull && docker compose build && docker compose up -d

# Logs
docker logs -f orion

# Health check
curl http://127.0.0.1:8087/health

# Restart
docker compose restart
```

The container binds to `0.0.0.0:8087` (LAN-accessible). The `/chat` endpoint
requires a bearer token (`HAL_WEB_TOKEN` in `.env`). `GET /`, `/static/*`, and
`/health` are unauthenticated so the Web UI can load and monitoring tools can
probe health. It uses `restart: unless-stopped` so it survives reboots as long
as Docker starts.

### Rollback to bare-metal

If the container has issues, rollback takes 2 minutes:

```bash
docker compose down
systemctl --user enable --now server.service
systemctl --user enable --now telegram.service
```

The old unit files are disabled but not deleted.

### Enable linger (required for user systemd to survive logout)

```bash
loginctl enable-linger jp
```

Without this, user systemd units stop when the SSH session ends.

---

## Ollama GPU flag (critical)

`OLLAMA_NUM_GPU=0` must be set in `/etc/systemd/system/ollama.service.d/override.conf`.

This is not a performance flag — it prevents Ollama from consuming ~800 MB VRAM that vLLM
needs for the KV cache. Without it, vLLM OOMs during inference on the RTX 3090 Ti.

```bash
# Verify
systemctl cat ollama | grep OLLAMA_NUM_GPU
# Should show: OLLAMA_NUM_GPU=0
```

---

## Tracing (OTel → Grafana Tempo)

HAL emits OpenTelemetry traces via `hal/tracing.py`. Grafana Tempo receives them
over OTLP HTTP on port 4318. Traces are viewable in Grafana.

### Deploy

Run the deploy script from the Orion repo root on the server:

```bash
bash ops/deploy-tempo.sh
```

This copies `ops/tempo.yaml` and the Grafana datasource provisioning file to
the monitoring stack, then restarts it. See the script for the docker-compose
service snippet to add manually.

### HAL configuration

HAL's container reaches Tempo via `host.docker.internal`:

```bash
# In ~/orion/.env
OTLP_ENDPOINT=http://host.docker.internal:4318
```

Then restart HAL: `docker compose restart` (in `~/orion/`).

### Verify end-to-end trace flow

1. **Tempo is running:**

   ```bash
   docker ps | grep tempo
   curl -s http://localhost:3200/ready   # should print "ready"
   ```

2. **HAL tracing is enabled** — look for this in `docker logs orion`:

   ```text
   Tracing enabled -> http://host.docker.internal:4318
   ```

   If you see `OTLP endpoint unreachable` instead, Tempo isn't reachable from
   the HAL container.

3. **Traces appear in Grafana:**
   - Open `http://192.168.5.10:3001` → Explore → select **Tempo** datasource
   - Search tab → Service Name: `hal` → Run query
   - Traces should appear after any HAL interaction (REPL, HTTP `/chat`, Telegram)

4. **Expected span names** (nested hierarchy):

   | Span | Source | Description |
   | --- | --- | --- |
   | `hal.turn` | `hal/main.py` | One full REPL turn |
   | `hal.run_agent` | `hal/agent.py` | Entire agent loop (up to 8 iterations) |
   | `hal.intent.classify` | `hal/intent.py` | Embedding-based intent classification |
   | `hal.tool_call` | `hal/agent.py` | Individual tool execution within the loop |
   | `hal.llm.chat_with_tools` | `hal/llm.py` | LLM call with tool definitions |
   | `hal.llm.chat` | `hal/llm.py` | Plain LLM call (no tools) |

### Retention

Tempo is configured with 7-day retention (`ops/tempo.yaml`). Older traces are
automatically compacted away.

---

## Known traps

**Prometheus port:** 9091 is Prometheus. 9090 is Cockpit. They are different services.
The `PROMETHEUS_URL` default in `config.py` is `http://192.168.5.10:9091`. The `.env`
override must also be `9091`. Do not "fix" it to 9090.

**SQLite init race:** If HAL crashes between opening `~/.orion/memory.db` and completing
schema init, the file is left as an empty schema-0 database. Next start fails with
`sqlite3.OperationalError: disk I/O error`. Fix:

```bash
rm ~/.orion/memory.db   # HAL recreates it on next launch
```

**Ollama model param removed (Feb 2026):** `OllamaClient.__init__` no longer takes a
`model` argument. Signature is `(base_url, embed_model)`. Any code constructing it with
three args will break.

**Falco `pg_isready` noise:** Falco fires `Read sensitive file untrusted` every ~30s
because the pgvector healthcheck reads `/etc/shadow`. This is a known false positive
filtered by default in `hal/falco_noise.py`. Do not suppress the rule globally in Falco.

**vLLM path in unit file:** `ops/vllm.service` contains an absolute path
(`/home/jp/vllm-env/bin/vllm`). If the venv location changes or the user is different,
edit the unit file before deploying.

**OTLP tracing probe at startup:** HAL TCP-probes the OTLP endpoint once at startup.
With Tempo deployed, set `OTLP_ENDPOINT=http://host.docker.internal:4318` in `.env`
so the probe succeeds from inside the HAL container. If Tempo goes down, the probe
fails, tracing is skipped silently (DEBUG log only), and no background exporter thread
runs. The 1-second timeout adds ~1 second to startup. To skip the probe entirely, set
`OTEL_SDK_DISABLED=true` in `.env`.

**Swap on zram0 — not a leak:** The server uses `/dev/zram0` (8 Gi compressed in-RAM
swap, not a disk partition). A few hundred MiB "used" there is normal — the kernel
compresses cold pages into RAM itself. `vm.swappiness=10` ensures the kernel strongly
prefers RAM; with 62 Gi total and typically only 6–8 Gi in active RSS, actual disk swap
pressure never occurs. If `swapon -s` shows zram0 near capacity (~8 Gi used), the real
culprit is the vLLM engine process (3–4 Gi RSS) combined with large buff/cache; reducing
`--gpu-memory-utilization` in `ops/vllm.service` from 0.95 is the correct lever. Do not
disable zram — removing it would not free RAM.

**EXTRA_HOSTS SSH keys:** Each host in `EXTRA_HOSTS` must have passwordless SSH access
from the HAL server (or container). Verify with `ssh -o BatchMode=yes user@host hostname`.
If HAL runs inside Docker, the SSH key must be mounted into the container. An unreachable
host will raise `ValueError` at tool-call time, not at startup — startup succeeds even if
a host is temporarily down.

---

## Secrets

Managed by SOPS + `homelab-secrets.service` (tmpfs at `/run/homelab-secrets/`).

Secret files available at runtime:

- `monitoring-stack.env` — Grafana credentials
- `pgvector-kb.env` — pgvector DB password
- `agent-zero.env` — (legacy, unused)

HAL reads the pgvector password from `PGVECTOR_DSN` in `.env`. If rotating the DB password,
update both SOPS secrets and the server `.env`.
