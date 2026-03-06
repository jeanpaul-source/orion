# Orion Containerization Plan

> **Purpose:** This document is an implementation plan for running HAL
> inside a Docker container with defense-in-depth isolation. It is a
> single-phase effort (one session of mostly operational work, ~2-3 hours
> active + 24h soak test). A new chat session should be able to read the
> preamble + one block of items and implement them without needing the full
> conversation history that produced this plan.
>
> **Created:** 2026-03-05 — based on the security gap analysis that
> identified `executor.py`'s `subprocess.run(shell=True)` as the primary
> risk surface. HAL runs as user `jp` with full permissions; the Judge is
> the only barrier.
>
> **Status:** Blocks A–F complete. 24-hour soak test in progress (started
> 2026-03-05 ~17:30). Verification due ~2026-03-06 18:30.
>
> **Priority:** Before all other feature work (multi-host SSH, Agent Zero,
> MCP). Build the walls before expanding the territory.
>
> **Guiding principle:** Three layers of defense, none of which needs to be
> perfect — they cover each other's gaps:
>
> ```
> Layer 1: The Judge (software gate — catches ~99% of dangerous commands)
> Layer 2: SSH service account (OS permissions — limits what the 1% can do)
> Layer 3: Container boundary (isolation — limits blast radius of total failure)
> ```

---

## Table of Contents

- [Orion Containerization Plan](#orion-containerization-plan)
  - [Table of Contents](#table-of-contents)
  - [How to use this file](#how-to-use-this-file)
    - [Starting work](#starting-work)
    - [Tracking progress](#tracking-progress)
    - [Updating the plan](#updating-the-plan)
    - [Governance](#governance)
  - [Preamble — paste this into every new chat](#preamble--paste-this-into-every-new-chat)
  - [Architecture after containerization](#architecture-after-containerization)
  - [Block A — Host Setup](#block-a--host-setup)
    - [Items](#items)
  - [Block B — Container Build](#block-b--container-build)
    - [Items](#items-1)
  - [Block C — Code Changes](#block-c--code-changes)
    - [Items](#items-2)
  - [Block D — Test \& Verify](#block-d--test--verify)
    - [Items](#items-3)
  - [Block E — Cutover](#block-e--cutover)
    - [Items](#items-4)
  - [Block F — Documentation \& Soak](#block-f--documentation--soak)
    - [Items](#items-5)
  - [Open Questions](#open-questions)
    - [Q1: hal-svc write access scope — RESOLVED: (A)](#q1-hal-svc-write-access-scope--resolved-a)
    - [Q2: Harvest execution location — RESOLVED: neither (stays on host)](#q2-harvest-execution-location--resolved-neither-stays-on-host)
    - [Q3: Read-only root filesystem — DEFERRED](#q3-read-only-root-filesystem--deferred)
    - [Q4: Network isolation — DEFERRED](#q4-network-isolation--deferred)
  - [Rollback Plan](#rollback-plan)
  - [Dependency Graph](#dependency-graph)
  - [Appendix A — Dockerfile](#appendix-a--dockerfile)
  - [Appendix B — Docker Compose](#appendix-b--docker-compose)
  - [Appendix C — Supervisord Config](#appendix-c--supervisord-config)
  - [Appendix D — Sudoers File](#appendix-d--sudoers-file)
  - [Appendix E — Filesystem Mounts](#appendix-e--filesystem-mounts)
    - [Design principle](#design-principle)
    - [Mount table](#mount-table)
    - [What is NOT mounted (and why)](#what-is-not-mounted-and-why)
  - [Appendix F — SSH \& Host Execution Design](#appendix-f--ssh--host-execution-design)
    - [Current state (the problem)](#current-state-the-problem)
    - [After containerization](#after-containerization)
    - [Why SSH, not Docker exec from inside?](#why-ssh-not-docker-exec-from-inside)
    - [Latency impact](#latency-impact)
    - [Path remapping for file reads (C2)](#path-remapping-for-file-reads-c2)
  - [Commit History](#commit-history)
  - [Revision Log](#revision-log)

---

## How to use this file

### Starting work

1. Open a **new chat window** (fresh context).
2. Paste the **Preamble** section below — it gives the AI enough project
   context to work without re-auditing the codebase.
3. Paste the **Block** you want to work on (A through F).
4. Work through the items. Each item follows CLAUDE.md format: root cause →
   proposal → approval → implement → test → commit.

### Tracking progress

Each item has a checkbox. Update this file as you go:

- `[ ]` — not started
- `[~]` — in progress / partially done
- `[x]` — done (include commit hash)
- `[!]` — needs revision (add a note explaining what changed)

### Updating the plan

If implementation reveals that a later item needs to change:

1. Mark the affected item with `[!]`.
2. Add a `> **Revision (date):**` blockquote under the item explaining
   what changed and why.
3. Do NOT delete the original text — future sessions need to see what was
   planned vs. what actually happened.

### Governance

CLAUDE.md rules apply to every step. Each item = one commit. Propose →
approve → implement → test → commit. No batching without explicit operator
permission.

---

## Preamble — paste this into every new chat

```text
You are working on Orion, a homelab AI assistant at /home/jp/orion.

Key docs (read before changing anything):
- CLAUDE.md — required format before every code change (proposal → approval → implement)
- ARCHITECTURE.md — component map, data flow
- OPERATIONS.md — lab host details, services, .env reference, known traps
- CONTRIBUTING.md — git workflow, test commands

Architecture summary:
- Chat LLM: VLLMClient → vLLM port 8000 → Qwen2.5-32B-Instruct-AWQ
- Embeddings: OllamaClient → Ollama port 11434 → nomic-embed-text (CPU only, GPU=0)
- Intent routing: IntentClassifier → dispatch_intent() in hal/bootstrap.py
  - "conversational" → _handle_conversational() (single LLM call, no tools)
  - everything else → run_agent() (full tool loop, KB + Prometheus pre-seeded)
- Judge (hal/judge.py): tier 0-3 policy gate, audit log at ~/.orion/audit.log
- Executor (hal/executor.py): subprocess.run(shell=True) locally, SSH for remote hosts
  - _LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
- Server (hal/server.py): FastAPI on port 8087, ServerJudge auto-denies tier 1+
- Telegram (hal/telegram.py): polls Telegram API, POSTs to /chat endpoint
- Server: the-lab (192.168.5.10), Fedora 43, RTX 3090 Ti, 64GB RAM, user systemd services

Commands:
  pytest tests/ --ignore=tests/test_intent.py -v    # offline tests
  ruff check hal/ tests/                              # lint
  git commit uses pre-commit hooks (ruff, format, markdownlint, mypy, doc-drift)
  git push runs pre-push hooks (full pytest with coverage)

You are implementing the Orion containerization plan.
Read notes/containerization-plan.md for full context, then work on the specific
block you are given.

The goal: move HAL into a Docker container so that even if the Judge fails, the
blast radius is limited to what the container can see and write. HAL reaches the
host via SSH to a restricted `hal-svc` service account. Three layers of defense:
Judge (software) → hal-svc (OS permissions) → container (isolation).
```

---

## Architecture after containerization

```
┌────────────────────────────────────────────────────────────────────┐
│  the-lab (host)                                                    │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  orion container (Docker)                                    │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌───────────┐  ┌──────────────────────┐  │  │
│  │  │  HTTP server  │  │  Telegram  │  │  REPL (docker exec)  │  │  │
│  │  │  (port 8087)  │  │  bot       │  │  interactive TTY     │  │  │
│  │  └──────┬───────┘  └─────┬─────┘  └──────────┬───────────┘  │  │
│  │         │                │                    │              │  │
│  │         ▼                ▼                    ▼              │  │
│  │  ┌──────────────────────────────────────────────────┐       │  │
│  │  │            HAL agent loop + Judge                 │       │  │
│  │  │  • Intent classifier                             │       │  │
│  │  │  • Tool dispatch                                 │       │  │
│  │  │  • KB search (pgvector over network)             │       │  │
│  │  │  • Prometheus queries (over network)             │       │  │
│  │  │  • Audit log writes (~/.orion/ — mounted RW)     │       │  │
│  │  └──────────────────────┬───────────────────────────┘       │  │
│  │                         │                                    │  │
│  │                    SSH (dedicated key)                        │  │
│  │                         │                                    │  │
│  └─────────────────────────┼────────────────────────────────────┘  │
│                            │                                       │
│                            ▼                                       │
│  ┌──────────────────────────────────────────┐                      │
│  │  hal-svc@the-lab (restricted user)       │                      │
│  │  • sudoers allow: read-only commands     │                      │
│  │  • sudoers allow: specific service mgmt  │                      │
│  │  • sudoers deny: everything else         │                      │
│  │  • no password, SSH key auth only        │                      │
│  └──────────────────────────────────────────┘                      │
│                                                                    │
│  Other services (unchanged, bare metal / Docker as today):         │
│  vLLM :8000  Ollama :11434  pgvector :5432  Prometheus :9091       │
│  Grafana :3001  Pushgateway :9092  ntopng :3000  Falco (eBPF)     │
└────────────────────────────────────────────────────────────────────┘
```

**Key change:** HAL no longer runs directly on the host. It lives in a container
and reaches the host via SSH to a restricted service account. Network services
(vLLM, Ollama, pgvector, Prometheus) are accessed over the Docker network — same
as today, just from inside the container.

**What goes in the container:** Everything — HTTP server, Telegram bot, and REPL.
One container, three entry points. HTTP + Telegram run via supervisord. REPL via
`docker exec -it orion python -m hal`.

---

## Block A — Host Setup

**Goal:** Create the `hal-svc` service account, SSH key pair, sudoers rules, and
sshd config on the host. This is all manual ops work on `the-lab` — no code changes.

**Estimated effort:** 20 minutes

**Prerequisites:** None. Can be done independently of everything else.

### Items

- [x] **A1 — Create `hal-svc` system user**

  ```bash
  sudo useradd -r -s /bin/bash -m hal-svc
  sudo usermod -aG docker hal-svc
  sudo usermod -aG systemd-journal hal-svc
  ```

  Give it a real shell (`/bin/bash`) — security comes from sudoers and the SSH
  key being inside the container, not from `nologin`. No password is set, so
  password-based SSH is impossible.

  Verify: `id hal-svc` shows `docker` and `systemd-journal` groups.

- [x] **A2 — Generate dedicated SSH key pair**

  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/hal-svc -N "" -C "hal-svc@orion-container"
  sudo mkdir -p /home/hal-svc/.ssh
  sudo cp ~/.ssh/hal-svc.pub /home/hal-svc/.ssh/authorized_keys
  sudo chown -R hal-svc:hal-svc /home/hal-svc/.ssh
  sudo chmod 700 /home/hal-svc/.ssh
  sudo chmod 600 /home/hal-svc/.ssh/authorized_keys
  ```

  Private key stays at `~/.ssh/hal-svc` (owned by `jp`). It gets mounted into
  the container read-only. `hal-svc` never sees its own private key.

  Verify: `ssh -i ~/.ssh/hal-svc hal-svc@localhost "whoami && id"`

- [x] **A3 — Install sudoers rules**

  Create `/etc/sudoers.d/hal-svc` — see [Appendix D](#appendix-d--sudoers-file)
  for the full file.

  The sudoers file permits read-only inspection commands (journalctl, systemctl
  status, docker ps/logs/inspect) and scoped service management (systemctl
  restart, docker restart). It does NOT permit destructive commands (rm, mv,
  shell access, package management, user management).

  ```bash
  sudo visudo -cf /etc/sudoers.d/hal-svc   # syntax check
  ```

  Verify: `ssh -i ~/.ssh/hal-svc hal-svc@localhost "sudo docker ps --format '{{.Names}}'"`
  Verify deny: `ssh -i ~/.ssh/hal-svc hal-svc@localhost "sudo rm -rf /tmp/test"` → denied

- [x] **A4 — Configure sshd for `hal-svc`**

  Create `/etc/ssh/sshd_config.d/hal-svc.conf`:

  ```
  Match User hal-svc
      AllowAgentForwarding no
      AllowTcpForwarding no
      X11Forwarding no
      PermitTTY yes
  ```

  ```bash
  sudo systemctl reload sshd
  ```

  Verify: SSH still works after reload.

- [x] **A5 — Symlink ~/.orion for hal-svc**

  > **Added (2026-03-05):** System prompt references `~/.orion/` paths
  > (watchdog state, watchdog log, harvest timestamp). When commands run
  > via SSH as `hal-svc`, `~` resolves to `/home/hal-svc/`. Without this
  > symlink, `cat ~/.orion/watchdog.log` fails on the host.

  ```bash
  sudo ln -s /home/jp/.orion /home/hal-svc/.orion
  ```

  Verify: `ssh -i ~/.ssh/hal-svc hal-svc@localhost "cat ~/.orion/audit.log | head -1"`

---

## Block B — Container Build

**Goal:** Create Dockerfile, docker-compose.yml, and supervisord.conf. Build the
image. No code changes yet — just the container infrastructure files.

**Estimated effort:** 30 minutes

**Prerequisites:** None. Can be done in parallel with Block A.

### Items

- [x] **B1 — Write Dockerfile** (`2520cb9`)

  Create `Dockerfile` in the repo root. See [Appendix A](#appendix-a--dockerfile)
  for the full file.

  Key decisions:
  - `python:3.12-slim` base (not Alpine — `psycopg2` needs `libpq-dev`/`gcc`)
  - Non-root `hal` user inside the container
  - SSH config baked in for `host.docker.internal` → `hal-svc`
  - `~/.orion/` created for standalone use (overridden by mount in compose)

  Files to create: `Dockerfile`

- [x] **B2 — Write docker-compose.yml** (`2520cb9`)

  Create `docker-compose.yml` in the repo root. See [Appendix B](#appendix-b--docker-compose)
  for the full file.

  Key decisions:
  - Port `127.0.0.1:8087:8087` (localhost only — no auth on HTTP API)
  - `~/.orion/` is the **only** read-write mount
  - Codebase, `.env`, infra configs, Falco logs, host `/etc/`, SSH key all read-only
  - Memory limit 2G, CPU limit 4 cores
  - 120s health check start_period (vLLM cold boot takes 60-90s)
  - `LAB_HOST=host.docker.internal` + `LAB_USER=hal-svc` force SSH mode

  Files to create: `docker-compose.yml`

- [x] **B3 — Write supervisord config** (`2520cb9`)

  Create `ops/supervisord.conf`. See [Appendix C](#appendix-c--supervisord-config)
  for the full file.

  Manages two processes inside the container: HTTP server and Telegram bot.
  Both auto-restart. Logs go to stdout/stderr (visible via `docker logs`).

  Files to create: `ops/supervisord.conf`

- [x] **B4 — Build the image** (`2520cb9`)

  ```bash
  cd ~/orion && docker compose build
  ```

  Verify: `docker images | grep orion` shows the built image.

---

## Block C — Code Changes

**Goal:** Minimal code changes to make HAL work from inside a container. Total
estimated change: ~20 lines in existing files.

**Estimated effort:** 30 minutes

**Prerequisites:** None. Can be done before or after Blocks A/B.

### Items

- [x] **C1 — Falco log path environment variable** (`234668a`)

  **File:** `hal/security.py`
  **Change:** Make the Falco log path configurable:

  ```python
  FALCO_LOG = os.environ.get("FALCO_LOG_PATH", "/var/log/falco/events.json")
  ```

  Inside the container, set `FALCO_LOG_PATH=/mnt/falco/events.json` (the mount
  point). On bare metal, the default works unchanged.

  Tests: existing security tests should pass. Add a test that verifies the env
  var override.

- [x] **C2 — File reads via SSH** (no code change needed)

  **File:** `hal/workers.py` (and possibly `hal/tools.py`)
  **Change:** When running inside the container, `read_file` and `list_dir` should
  use the SSH executor to read files from the host, rather than local `cat`/`ls`.

  Rationale: paths like `/etc/systemd/system/falco.service` don't exist inside
  the container. The host filesystem is only partially mounted. SSH to `hal-svc`
  can read any path the service account has permission to access.

  Alternative considered: path remapping (e.g. `/etc/` → `/mnt/host-etc/`). Rejected
  — adds mapping logic that must stay in sync with compose mounts. SSH is simpler
  and more general. The ~50ms latency per file read is acceptable.

  Tests: mock the executor, verify file reads go through SSH when `LAB_HOST` is
  not in `_LOCAL_HOSTS`.

- [x] **C3 — System prompt path references** (no code change; resolved by A5 symlink)

  **File:** `hal/bootstrap.py`
  **Change:** Update any hardcoded path references in the system prompt to reflect
  container mount points, or make them relative. Scope TBD during implementation —
  read `SYSTEM_PROMPT` in `bootstrap.py` and check for absolute paths.

  Tests: verify system prompt renders without errors.

---

## Block D — Test & Verify

**Goal:** Start the container and verify every interface, security boundary, and
tool path works correctly.

**Estimated effort:** 45 minutes

**Prerequisites:** Blocks A, B, and C all completed.

### Items

- [x] **D1 — Start container and verify health endpoint**

  ```bash
  docker compose up -d && docker compose logs -f
  ```

  Wait for startup. Then:

  ```bash
  curl http://localhost:8087/health
  ```

  Expected: `{"status": "ok", ...}`

- [x] **D2 — Verify REPL via docker exec**

  ```bash
  docker exec -it orion python -m hal --new
  ```

  Test queries:
  - "What services are running?" — should produce results via SSH commands
  - "What's in /opt/homelab-infrastructure?" — should produce results
  - `/quit` to exit

  Verify: Judge y/N prompts still work (TTY is attached via `docker exec -it`).

- [x] **D3 — Verify chat endpoint**

  ```bash
  curl -X POST http://localhost:8087/chat \
    -H 'Content-Type: application/json' \
    -d '{"message": "How is the lab doing?"}'
  ```

  Expected: a real response (not an error).

- [x] **D4 — Verify security boundaries**

  ```bash
  # Container cannot write to read-only mounts
  docker exec orion touch /app/test
  # Expected: Read-only file system

  # Container cannot see unmounted paths
  docker exec orion ls /home/jp/
  # Expected: No such file or directory

  # Docker socket is NOT mounted
  docker exec orion ls /var/run/docker.sock
  # Expected: No such file or directory
  ```

  Then via the REPL, test that destructive commands fail at the OS level:
  ```
  "Run the command: rm -rf /home/jp/important-stuff"
  → Expected: Permission denied (hal-svc cannot access /home/jp/)
  ```

- [x] **D5 — Run test suite inside container**

  ```bash
  docker exec orion python -m pytest tests/ --ignore=tests/test_intent.py -v
  ```

  Some tests may need adjustment (mocked executors should work; tests that assume
  localhost execution may need updates). Fix any failures before proceeding.

- [x] **D6 — Verify Telegram bot**

  Send a message to the Telegram bot. Verify it responds. Check audit log:

  ```bash
  docker exec orion tail -5 /home/hal/.orion/audit.log
  ```

---

## Block E — Cutover

**Goal:** Switch production from bare-metal systemd units to the container. Set up
harvest/watchdog to use `docker exec`. Create the `hal` shell alias.

**Estimated effort:** 20 minutes

**Prerequisites:** Block D passed (everything verified).

### Items

- [x] **E1 — Disable old systemd units**

  ```bash
  systemctl --user disable --now server.service
  systemctl --user disable --now telegram.service
  ```

  Do NOT delete the unit files — they're the rollback path.

- [x] **E2 — Update harvest timer** (no change — stays on host venv)

  > **Deviation:** Plan called for `docker exec orion python -m harvest`.
  > Harvest needs direct host access (Docker socket, `systemctl cat`,
  > `Path.read_text()` on host paths). Inside the container it only
  > collected 13 chunks from 6 docs (vs 17,250 from 1,272 on host).
  > Harvest stays on the host venv unchanged — it's a host-monitoring
  > tool, not part of HAL's chat/agent.

- [x] **E3 — Update watchdog timer** (no change — stays on host venv)

  > **Deviation:** Same as E2. Watchdog reads `/var/log/falco` and uses
  > host `Path.home()`. Stays on host venv unchanged.

- [x] **E4 — Shell alias**

  Add to `~/.bashrc`:

  ```bash
  alias hal='docker exec -it orion python -m hal'
  ```

  Verify: open a new terminal, type `hal`, confirm REPL starts.

- [x] **E5 — Deploy alias**

  Add to `~/.bashrc`:

  ```bash
  alias orion-deploy='cd ~/orion && git pull && docker compose build && docker compose up -d'
  ```

  Previous deploy workflow: `git pull && systemctl --user restart server.service`
  New deploy workflow: `orion-deploy`

---

## Block F — Documentation & Soak

**Goal:** Update docs to reflect the new architecture. Run for 24 hours and verify
everything is stable.

**Estimated effort:** 20 minutes active + 24 hours soak

**Prerequisites:** Block E completed (running in production on the container).

### Items

- [x] **F1 — Update OPERATIONS.md** (`5d35109`)

  Updated deploy instructions, systemd unit references, log access commands, and
  the services table to reflect Docker Compose deployment.

  Files changed: `OPERATIONS.md`

- [x] **F2 — Update CLAUDE.md current state** (`5d35109`)

  Updated "Current State" section to note HAL runs in a container.

  Files changed: `CLAUDE.md`

- [x] **F3 — Update README.md** (`5d35109`)

  Updated quick-start instructions and key files table to reflect container
  deployment.

  Files changed: `README.md`

- [~] **F4 — 24-hour soak test** (started 2026-03-05 ~17:30)

  **T+26 minute baseline:**

  | Check | Value |
  |---|---|
  | Container status | Up 26m (healthy) |
  | Health endpoint | `{"status":"ok"}` |
  | Restart count | 0 |
  | Audit log | 83 entries |
  | Telegram polls (30s window) | 5 successful |
  | Harvest timer | Next: 2026-03-06 03:00 |
  | Watchdog timer | Every 5 min, active |

  **24h verification commands** (run ~2026-03-06 18:30):

  ```bash
  docker ps | grep orion                              # still running?
  curl http://127.0.0.1:8087/health                   # still healthy?
  docker inspect orion --format '{{.RestartCount}}'   # should be 0
  wc -l ~/.orion/audit.log                            # growing (watchdog writes)
  journalctl --user -u harvest.service --since "03:00" | tail -5  # 3am harvest ran?
  docker logs --since 1m orion 2>&1 | grep -c '200 OK'  # telegram still polling?
  ```

  If all checks pass, mark this `[x]` — containerization is complete.

---

## Open Questions

Decisions to make before or during implementation:

### Q1: hal-svc write access scope — RESOLVED: (A)

Kept as designed — Judge + sudoers are two independent layers. `hal-svc` has
OS-level permission for service management; the Judge gates at tier 1.

### Q2: Harvest execution location — RESOLVED: neither (stays on host)

Neither (A) nor (B). Harvest and watchdog stay on the **host venv** — they
need direct system access (Docker socket, systemd, host filesystem). See
revision notes on E2/E3.

### Q3: Read-only root filesystem — DEFERRED

Not yet implemented. Add `--read-only` + tmpfs as a future hardening step
after the soak test confirms stability.

### Q4: Network isolation — DEFERRED

Default bridge network. Container needs ~10 outbound connections. Restricting
them would be complex for marginal benefit. `web.py` SSRF protection covers
the fetch_url path.

---

## Rollback Plan

If containerization causes problems, rollback takes 2 minutes:

```bash
docker compose down
systemctl --user enable --now server.service
systemctl --user enable --now telegram.service
# Revert harvest/watchdog ExecStart if changed
systemctl --user daemon-reload
```

Bare-metal code is unchanged. `.env` changes (`LAB_HOST`, `LAB_USER`) revert to
`localhost` / `jp`. Systemd unit files are not deleted — just re-enable them.

---

## Dependency Graph

```
Block A (host setup)          Block B (container build)     Block C (code changes)
  A1: create hal-svc            B1: Dockerfile                C1: Falco path env var
  A2: SSH key pair              B2: docker-compose.yml        C2: file reads via SSH
  A3: sudoers rules             B3: supervisord.conf          C3: system prompt paths
  A4: sshd config               B4: build image
       │                             │                             │
       └──────────────┬──────────────┘─────────────────────────────┘
                      │
                      ▼
               Block D (test & verify)
                 D1: health endpoint
                 D2: REPL via exec
                 D3: chat endpoint
                 D4: security boundaries
                 D5: test suite in container
                 D6: Telegram bot
                      │
                      ▼
               Block E (cutover)
                 E1: disable systemd units
                 E2: harvest timer
                 E3: watchdog timer
                 E4: shell alias
                 E5: deploy alias
                      │
                      ▼
               Block F (docs & soak)
                 F1: OPERATIONS.md
                 F2: CLAUDE.md
                 F3: README.md
                 F4: 24h soak test
```

**Blocks A, B, C are independent** — can be done in any order or in parallel.
Blocks D → E → F are sequential.

---

## Appendix A — Dockerfile

```dockerfile
# Orion HAL container
FROM python:3.12-slim

# System dependencies for SSH client and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user inside the container
RUN useradd -m -s /bin/bash hal

# Application directory
WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install supervisor for multi-process management
RUN pip install --no-cache-dir supervisor

# Copy application code (overridden by read-only mount in compose)
COPY . .

# SSH config for the service account
RUN mkdir -p /home/hal/.ssh && \
    echo "Host the-lab\n  HostName host.docker.internal\n  User hal-svc\n  IdentityFile /home/hal/.ssh/id_ed25519\n  StrictHostKeyChecking accept-new\n  BatchMode yes\n  ConnectTimeout 5" \
    > /home/hal/.ssh/config && \
    chown -R hal:hal /home/hal/.ssh && \
    chmod 700 /home/hal/.ssh && \
    chmod 600 /home/hal/.ssh/config

# State directory (overridden by mount, but create for standalone use)
RUN mkdir -p /home/hal/.orion && chown hal:hal /home/hal/.orion

USER hal

# Default: supervisord manages HTTP server + Telegram bot
CMD ["supervisord", "-c", "/app/ops/supervisord.conf"]
```

**Why python:3.12-slim, not Alpine?** `psycopg2` needs `libpq-dev` + `gcc` which
are painful on Alpine. Image size difference (~150MB vs ~80MB) is irrelevant on a
64GB server. Python 3.12 matches project target (`pyproject.toml`, mypy config).

**Why non-root?** If there's a container escape, the attacker lands as `hal` not
root. Root inside a container can often map to root on the host.

---

## Appendix B — Docker Compose

```yaml
# ~/orion/docker-compose.yml
services:
  hal:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: orion
    restart: unless-stopped

    extra_hosts:
      - "host.docker.internal:host-gateway"

    ports:
      - "127.0.0.1:8087:8087"

    volumes:
      # HAL's state — the ONLY read-write mount
      - /home/jp/.orion:/home/hal/.orion:rw

      # Codebase — read-only (LLM cannot modify its own code)
      - /home/jp/orion:/app:ro

      # Config (secrets) — read-only single file
      - /home/jp/orion/.env:/app/.env:ro

      # Infrastructure configs — read-only
      - /opt/homelab-infrastructure:/mnt/infra:ro

      # Reference documents — read-only
      - /data/orion:/mnt/data:ro

      # Falco logs — read-only
      - /var/log/falco:/mnt/falco:ro

      # Host system configs — read-only
      - /etc:/mnt/host-etc:ro

      # SSH key for service account — read-only
      - /home/jp/.ssh/hal-svc:/home/hal/.ssh/id_ed25519:ro

    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "4"

    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8087/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s

    security_opt:
      - label:disable    # SELinux (Fedora 43): :z relabelling would break host services

    environment:
      - HOME=/home/hal
      - LAB_HOST=host.docker.internal
      - LAB_USER=hal-svc
```

**Why 127.0.0.1:8087?** HAL's HTTP API has no auth. Localhost-only binding means
only the Telegram bot (same container) and local tools can reach it.

**Why 120s start_period?** vLLM takes 60-90s to load the model. HAL's startup
blocks until vLLM responds.

---

## Appendix C — Supervisord Config

```ini
; ops/supervisord.conf
[supervisord]
nodaemon=true
user=hal
logfile=/dev/stdout
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:server]
command=python -m hal.server --host 0.0.0.0
directory=/app
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:telegram]
command=python -m hal.telegram
directory=/app
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

**Why `--host 0.0.0.0`?** Inside a container, Docker port forwarding routes traffic
to the container's eth0 interface, not loopback. Binding to `127.0.0.1` (default)
makes the server unreachable from outside the container. Security is maintained by
compose's `127.0.0.1:8087:8087` host-side binding.

**Why logfile/pidfile overrides?** `/app` is a read-only mount. Supervisord's
defaults write to the working directory, which would fail. Log goes to stdout
(visible via `docker logs`), pid goes to `/tmp`.

---

## Appendix D — Sudoers File

```sudoers
# /etc/sudoers.d/hal-svc — scoped permissions for HAL service account

# Read-only system inspection (tier 0 equivalent)
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/journalctl --no-pager *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl status *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-enabled *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl list-units *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl list-timers *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl cat *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker ps *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker logs *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker inspect *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker stats --no-stream *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker info
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker compose -f * ps *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker compose -f * logs *

# Service management (tier 1 — Judge prompts in REPL, auto-denied in HTTP)
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/systemctl start *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker restart *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker stop *
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/docker start *

# Osquery
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/osqueryi *

# Nmap LAN scan (tier 1)
hal-svc ALL=(ALL) NOPASSWD: /usr/bin/nmap -sn *
```

**What is NOT permitted:** `rm`, `mv`, `cp`, `chmod`, `chown`, `mount`, `dd`,
`mkfs`, `/bin/bash`, `/bin/sh`, `apt`, `dnf`, `pip`, `useradd`, `usermod`,
`passwd`, `sudo su`, `sudo -i`, `sudo bash`.

---

## Appendix E — Filesystem Mounts

### Design principle

> HAL can READ almost everything. HAL can WRITE almost nothing.
> If it can see your files, it can answer questions. If it can't modify
> them, it can't destroy them.

### Mount table

| Host path | Container path | Mode | Purpose |
|---|---|---|---|
| `~/.orion/` | `/home/hal/.orion/` | **RW** | Audit log, memory.db, sessions, watchdog state |
| `~/orion/` | `/app/` | RO | Codebase (LLM cannot self-modify) |
| `~/orion/.env` | `/app/.env` | RO | Configuration and secrets |
| `/opt/homelab-infrastructure/` | `/mnt/infra/` | RO | Compose files, infra configs |
| `/data/orion/` | `/mnt/data/` | RO | Reference docs for harvest |
| `/var/log/falco/` | `/mnt/falco/` | RO | Falco security events |
| `/etc/` | `/mnt/host-etc/` | RO | System configs (systemd, network, etc.) |
| `~/.ssh/hal-svc` | `/home/hal/.ssh/id_ed25519` | RO | SSH key for `hal-svc` |

### What is NOT mounted (and why)

| Path | Reason |
|---|---|
| `~/.ssh/` (your keys) | HAL gets its own key, not yours |
| `/home/jp/` (broadly) | Not needed — HAL reads via SSH to `hal-svc` for unmounted paths |
| `/var/run/docker.sock` | Docker socket = root access. Never mount this. |
| `/run/homelab-secrets/` | SOPS tmpfs. HAL reads what it needs from `.env` |

---

## Appendix F — SSH & Host Execution Design

### Current state (the problem)

`hal/executor.py` detects `LAB_HOST=localhost` → runs `subprocess.run(command,
shell=True)` directly as user `jp`. No OS-level boundary.

### After containerization

`LAB_HOST=host.docker.internal` is not in `_LOCAL_HOSTS` → executor automatically
uses SSH mode. Commands SSH into the host as `hal-svc`. **Zero code changes needed
in executor.py** — the existing SSH path handles this.

### Why SSH, not Docker exec from inside?

| Approach | Trade-off |
|---|---|
| **SSH to hal-svc** | Existing code path. Unix permissions limit hal-svc. No socket needed. ~50-100ms latency. |
| **Docker socket** | Socket access ≈ root. Defeats the purpose. |
| **No host commands** | HAL can't run docker ps, journalctl, systemctl — too limiting. |

### Latency impact

50-100ms per SSH command. Max 5 tool calls per turn = ~500ms worst case. Imperceptible
when LLM inference takes 2-5 seconds. Prometheus/pgvector queries go over HTTP directly
(no SSH overhead for those).

### Path remapping for file reads (C2)

LLM asks to read `/etc/systemd/system/falco.service` → path doesn't exist inside the
container. Two options:

- **(A) SSH for all file reads** — simpler, no mapping code, ~50ms per read. **Chosen.**
- **(B) Local reads with path mapping** — faster but adds sync-sensitive mapping logic.

Option A is the starting point. If multi-file operations prove too slow, Option B can
be added as an optimization.

---

## Commit History

| Commit | Description |
|---|---|
| `2520cb9` | Block B — Dockerfile, compose, supervisord, .dockerignore |
| `234668a` | Block C1 — Falco path env var |
| `4887014` | Plan revision notes (B+C findings) |
| `186e7e6` | Fix: SELinux label:disable |
| `dd419eb` | Fix: supervisord log/pid to writable paths |
| `bad5b90` | Plan revision notes (D findings) |
| `83f4bf8` | Plan revision notes (E findings) |
| `5d35109` | Docs: OPERATIONS, CLAUDE, README updated |

---

## Revision Log

> Track plan changes here. Each entry should reference the item ID that
> changed and which chat session made the change.

> **Revision (2026-03-05, Block B+C implementation session):**
>
> **B1 — Dockerfile:** Changed `python:3.11-slim` → `python:3.12-slim`. Project
> targets Python 3.12 (pyproject.toml `target-version = "py312"`, mypy
> `python_version = "3.12"`, local Python is 3.12.3). Using 3.11 would be a
> downgrade that could break type hints or syntax.
>
> **B3 — Supervisord:** Changed server command from `python -m hal.server` to
> `python -m hal.server --host 0.0.0.0`. Inside a container, binding to
> `127.0.0.1` (the default) means Docker's port forwarding cannot reach the
> server — traffic is routed to the container's eth0 interface, not loopback.
> Security is maintained by compose's `127.0.0.1:8087:8087` host-side binding.
>
> **C1 — Falco path:** Implemented the env var (`FALCO_LOG_PATH`) but the
> docker-compose should NOT set it. Commands run via SSH on the host where
> `/var/log/falco/events.json` is the correct path. The `/mnt/falco/` mount
> is useful for future direct-read patterns but isn't used by current code.
>
> **C2 — File reads via SSH:** Confirmed no code changes needed. Verified
> `host.docker.internal` is not in `_LOCAL_HOSTS`, so executor routes all
> commands through SSH automatically.
>
> **C3 — System prompt paths:** No code changes needed, BUT discovered that
> `~/.orion/` references in the system prompt will break via SSH because `~`
> for `hal-svc` resolves to `/home/hal-svc/`, not `/home/jp/`. Fix: added
> item A5 (below) — symlink on the host.
>
> **A5 (new item) — Symlink ~/.orion for hal-svc:** Required for `~/.orion/`
> paths in the system prompt to work when commands run via SSH as `hal-svc`.
> Command: `sudo ln -s /home/jp/.orion /home/hal-svc/.orion`
>
> **B1 (addendum):** Added `.dockerignore` to keep build context small.

> **Revision (2026-03-05, Block D testing session):**
>
> **SELinux (Fedora 43):** Container crash-looped because SELinux (Enforcing)
> blocks `container_t` processes from accessing host-labeled volume mounts.
> Using `:z` relabelling on system dirs (`/etc`, `/var/log/falco`) would break
> host services by replacing their SELinux labels. Fix: added
> `security_opt: - label:disable` to compose. All other isolation layers
> (namespaces, cgroups, RO mounts, Judge, hal-svc) remain intact.
>
> **Supervisord log/pid:** supervisord defaults to writing its log and pid
> file in the working directory (`/app`), which is a read-only mount. Fix:
> set `logfile=/dev/stdout`, `logfile_maxbytes=0`, `pidfile=/tmp/supervisord.pid`
> in supervisord.conf.
>
> **Telegram conflict:** Old `telegram.service` systemd unit was still running,
> causing 409 Conflict errors. Stopped it manually; Block E will disable all
> old systemd units permanently.
>
> **Start-up time:** Server takes ~30s to connect to external services (vLLM,
> pgvector, Ollama) before responding to health checks. The 120s
> `start_period` in the health check configuration is sufficient.

> **Revision (2026-03-05, Block E cutover session):**
>
> **E2+E3 — Harvest & watchdog stay on host:** The plan called for
> `docker exec orion python -m harvest` and `docker exec orion python -m
> hal.watchdog`. This doesn't work — harvest uses `subprocess.run("docker
> ps")`, reads `/opt/homelab-infrastructure/` via `Path.read_text()`, calls
> `systemctl cat`, etc. All of these need direct host access. Inside the
> container, harvest only collected 13 chunks from 6 documents (vs 17,250
> from 1,272 on the host). Watchdog similarly reads `/var/log/falco` and
> uses host `Path.home()`. Both services **stay on the host venv** unchanged.
> This is correct: they're host-monitoring tools, not part of HAL's chat/agent.
>
> **E4 — hal alias updated:** `docker exec -it orion python -m hal` ✓
>
> **E5 — orion-deploy alias added:** `cd ~/orion && git pull && docker
> compose build && docker compose up -d` ✓
