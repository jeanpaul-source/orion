# Operations

Deploy, configure, and run Orion/HAL on the homelab server.

---

## Prerequisites

**On the machine running HAL (server or laptop with `USE_SSH_TUNNEL=true`):**

- Python 3.11+
- SSH key-based access to `LAB_HOST` (no password prompt on connect)

**On the server (`the-lab`, `192.168.5.10`):**

| Service | How it runs | Port | Notes |
| --- | --- | --- | --- |
| vLLM | user systemd `vllm.service` | 8000 | Chat LLM — must be fully loaded before starting HAL |
| Ollama | system systemd | 11434 | Embeddings only, CPU-bound — `OLLAMA_NUM_GPU=0` is load-bearing |
| pgvector | Docker | 5432 | PostgreSQL + pgvector extension |
| Prometheus | Docker | 9091 | **Not 9090** — port 9090 is Cockpit |
| Grafana | Docker | 3001 | |
| Pushgateway | Docker | 9092 | HAL metrics target |
| Falco | system systemd | — | `falco-modern-bpf.service`; JSON events at `/var/log/falco/events.json` |
| Osquery | bare metal | — | Version 5.21.0; `/etc/sudoers.d/osquery-hal` scoped to `osqueryi` only |
| ntopng | Docker Compose | 3000 | `~/ntopng/docker-compose.yml`; login disabled; Community API at `/lua/rest/v2/` |
| Nmap | bare metal | — | Version 7.92 |

---

## Setup

```bash
git clone https://github.com/jeanpaul-source/orion
cd orion
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `PGVECTOR_DSN` password from the server:

```bash
cat /run/homelab-secrets/pgvector-kb.env
```

Then run the initial harvest to populate the knowledge base:

```bash
python -m harvest
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
| `USE_SSH_TUNNEL` | `false` | Set `true` when running from a laptop |
| `NTFY_URL` | *(empty)* | Push alerts via ntfy.sh topic URL — leave empty to disable |
| `HAL_INSTANCE` | *(hostname)* | Grafana Pushgateway label — set `laptop` or `the-lab` explicitly |
| `PROM_PUSHGATEWAY` | *(empty)* | `http://localhost:9092` (server) or `http://192.168.5.10:9092` (laptop) |
| `HAL_LOG_JSON` | `1` | `1` = JSON logs, `0` = plain text |
| `HAL_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OTLP_ENDPOINT` | `http://localhost:4318` | OTel OTLP HTTP — no-op if unreachable |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | From @BotFather — leave empty to disable bot |
| `TELEGRAM_ALLOWED_USER_ID` | `0` | Numeric Telegram user ID — get from @userinfobot |

---

## Running HAL

```bash
# Continue last session
python -m hal

# Start fresh (new session, history cleared from context but DB kept)
python -m hal --new

# Server alias
hal     # expands to: cd ~/orion && .venv/bin/python -m hal
```

HAL's readline history is at `~/.orion/history`. Session DB at `~/.orion/memory.db`.

---

## Systemd units

All units are **user systemd** (not system). Required because the code lives in a home
directory and SELinux blocks system services from executing it.

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

### HAL HTTP server (`ops/server.service`)

FastAPI server that handles all `/chat` and `/health` requests. Required by the
Telegram bot — deploy and start this before `telegram.service`.

```bash
cp ops/server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now server.service
```

Wait for `HAL services connected — server ready` in the journal before starting the bot:

```bash
journalctl --user -u server -f
```

### Telegram bot (`ops/telegram.service`)

Long-running polling bot. Connects to the Telegram API and forwards messages to the
HTTP server at `localhost:8087`. Requires `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_ALLOWED_USER_ID` in `.env`. **Deploy `server.service` first.**

```bash
# Deploy (server.service must already be running)
cp ops/telegram.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now telegram.service

# Manage
systemctl --user status telegram.service
systemctl --user restart telegram.service
journalctl --user -u telegram -f
```

The bot is independently restartable — it does not affect the REPL or HTTP server.
If the HTTP server is down, the bot replies with "HAL server is offline."

`Type=simple` with `Restart=on-failure` and `RestartSec=15` — auto-recovers from
crashes without restart-looping.

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
filtered by default in `hal/security.py`. Do not suppress the rule globally in Falco.

**vLLM path in unit file:** `ops/vllm.service` contains an absolute path
(`/home/jp/vllm-env/bin/vllm`). If the venv location changes or the user is different,
edit the unit file before deploying.

**Swap on zram0 — not a leak:** The server uses `/dev/zram0` (8 Gi compressed in-RAM
swap, not a disk partition). A few hundred MiB "used" there is normal — the kernel
compresses cold pages into RAM itself. `vm.swappiness=10` ensures the kernel strongly
prefers RAM; with 62 Gi total and typically only 6–8 Gi in active RSS, actual disk swap
pressure never occurs. If `swapon -s` shows zram0 near capacity (~8 Gi used), the real
culprit is the vLLM engine process (3–4 Gi RSS) combined with large buff/cache; reducing
`--gpu-memory-utilization` in `ops/vllm.service` from 0.95 is the correct lever. Do not
disable zram — removing it would not free RAM.

---

## Secrets

Managed by SOPS + `homelab-secrets.service` (tmpfs at `/run/homelab-secrets/`).

Secret files available at runtime:

- `monitoring-stack.env` — Grafana credentials
- `pgvector-kb.env` — pgvector DB password
- `agent-zero.env` — (legacy, unused)

HAL reads the pgvector password from `PGVECTOR_DSN` in `.env`. If rotating the DB password,
update both SOPS secrets and the server `.env`.
