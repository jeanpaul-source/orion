# Production Code Audit — Findings

**Audited:** 2026-03-XX (Chat 12)
**Scope:** All 31 Python modules in `hal/` (8,544 lines), 6 modules in `harvest/` (~1,065 lines)
**Branch:** `main`

---

## Severity Definitions

| Level | Meaning |
|-------|---------|
| **P0** | Security hole or data-loss risk that can be triggered in production today |
| **P1** | Correctness bug, silent failure, or architectural issue that will bite eventually |
| **P2** | Code smell, inconsistency, or improvement that isn't urgent |

---

## P0 — Security / Data-Loss

### P0-1: Sandbox cleanup bypasses the Judge

**File:** [hal/sandbox.py](../hal/sandbox.py#L196)
**Investigation target:** A.1

The `execute_code()` function's `finally` block runs
`executor.run(f"rm -f {shlex.quote(host_code_path)}")` directly — no
`judge.approve()`, no `record_outcome()`, no audit log entry. This is a
shell command bypassing the Judge entirely. While the path is constructed
internally (not user-supplied) and `shlex.quote()` prevents injection,
it violates the project's core invariant: **every shell command goes through
the Judge**.

**Why it matters:** The audit log has a blind spot. If `executor.run()`
fails or hangs, there's no record. If the path construction is ever
refactored incorrectly, there's no safety net.

**Fix:** Call `judge.approve("run_command", cmd, reason="sandbox cleanup")`
before the `rm`. Since this is a benign tier-0 command, it will auto-approve
but still be audit-logged.

---

### P0-2: Sandbox Docker container missing `--cap-drop ALL` and `--no-new-privileges`

**File:** [hal/sandbox.py](../hal/sandbox.py#L88-L111)
**Investigation target:** D.1

`_build_docker_command()` uses `--network none`, `--read-only`,
`--memory 256m`, `--cpus 1`, `--pids-limit 64` — but omits two standard
container-hardening flags:

- `--cap-drop ALL` — without this, the sandbox inherits Docker's default
  capability set (14 capabilities including `CAP_NET_RAW`, `CAP_SYS_CHROOT`,
  `CAP_SETUID`, `CAP_SETGID`).
- `--security-opt no-new-privileges` — without this, a setuid binary inside
  the container could escalate.

**Why it matters:** The Dockerfile uses a non-root `sandbox` user, but:
(a) the `--user` flag is not passed in `_build_docker_command()` either
(see P0-3), so Docker runs as root inside the container; (b) even with a
non-root user, inherited capabilities widen the attack surface unnecessarily.

**Fix:** Add `--cap-drop`, `ALL`, `--security-opt`, `no-new-privileges` to the
command list in `_build_docker_command()`.

---

### P0-3: Sandbox Docker container runs as root (missing `--user` flag)

**File:** [hal/sandbox.py](../hal/sandbox.py#L88-L111)
**Investigation target:** D.2

The `Dockerfile.sandbox` creates a `sandbox` user, but `_build_docker_command()`
never passes `--user sandbox:sandbox`. The container process runs as root,
which defeats the purpose of the non-root user in the Dockerfile.

**Fix:** Add `--user`, `sandbox:sandbox` to the command list.

---

### P0-4: SSRF TOCTOU gap in `fetch_url()`

**File:** [hal/web.py](../hal/web.py#L100-L160)
**Investigation target:** E.1

`_validate_url()` resolves the hostname via `socket.getaddrinfo()` and checks
that all IPs are public. Then `requests.get()` re-resolves the hostname via
the OS resolver — a classic Time-of-Check/Time-of-Use (TOCTOU) race. If DNS
changes between the two lookups (DNS rebinding), `requests.get()` could fetch
from a private IP.

**Mitigating factors:**
- `fetch_url` is Judge tier 1, so it requires interactive approval in the
  REPL and is auto-denied in HTTP/Telegram mode.
- Redirect responses *are* revalidated via `_validate_url()` on each hop.
- An attacker would need to control a DNS server and time the rebind to the
  sub-second window between validation and request.

**Why it still matters:** The tier-1 gate mitigates the risk significantly,
but the TOCTOU gap is a known anti-pattern. If `fetch_url` is ever
trust-promoted to tier 0 (via the trust evolution system), the gap becomes
exploitable without human oversight.

**Fix:** Pin the resolved IP and use `requests.get()` with the IP directly
(setting the `Host` header to the original hostname).

---

## P1 — Correctness / Silent Failures

### P1-1: Prometheus client silently swallows all errors

**File:** [hal/prometheus.py](../hal/prometheus.py#L40-L95)
**Investigation target:** B.1

`query()`, `scalar()`, and `range_query()` all catch `Exception` and return
empty dict / `None` / empty list with **no logging at all**. When Prometheus
is misconfigured (wrong port, wrong URL, auth required), every query fails
silently. HAL reports "unavailable" for every metric with no clue about why.

**Why it matters:** This has already bitten the project (see SESSION_FINDINGS
D2 — `config.py` had port 9090 instead of 9091). With silent error
swallowing, the root cause was invisible. Any future Prometheus config issue
will be equally opaque.

**Fix:** Add `log.warning("Prometheus query failed: %s", exc)` in each
exception handler. Keep the graceful return (don't crash), but emit a
diagnostic breadcrumb.

---

### P1-2: Trust evolution silently disabled on corrupt audit log

**File:** [hal/judge.py](../hal/judge.py#L260-L290) (approx.)
**Investigation target:** B.3

`_load_trust_overrides()` catches `OSError` and returns `({}, frozenset())`.
If the audit log is corrupted, truncated, or has a permissions issue, all
trust evolution (both promotions and demotions) is silently disabled. The
Judge falls back to its static tier assignments with no warning.

**Why it matters:** Trust evolution is a core end-state capability (#5 on
the roadmap). Silent disablement means the operator thinks they have
adaptive autonomy when they actually have static tiers.

**Fix:** Log at WARNING level when `_load_trust_overrides()` falls back to
empty. Consider logging the count of successfully parsed events vs. parse
errors to signal partial corruption.

---

### P1-3: Audit log read in full on every Judge init — no rotation

**File:** [hal/judge.py](../hal/judge.py#L260-L290) (approx.)
**Investigation target:** G.3

`_load_trust_overrides()` reads the entire `~/.orion/audit.log` file every
time a `Judge` is instantiated. In the HTTP server, a new `Judge` is created
at startup, so this is one-time. But `WatchdogJudge` is created on every
watchdog run (every 5 minutes), and `_refresh_trust_overrides()` re-reads
the whole file.

Over months of operation, the audit log grows unboundedly. At ~200 bytes per
entry and ~100 entries/day, this is ~7 KB/day — manageable for months but
not indefinitely. More importantly, the O(n) parse on every watchdog run is
wasteful.

**Fix (short-term):** Add a `max_lines` parameter to
`_load_trust_overrides()` that only reads the last N lines (e.g., 10,000).
**Fix (long-term):** Implement log rotation with `logrotate` or a daily
truncation cron.

---

### P1-4: `run_command` outcomes not tracked for trust evolution

**Files:** [hal/tools.py](../hal/tools.py#L290-L310) (approx.),
[hal/main.py](../hal/main.py#L122-L133)
**Investigation target:** A.2 (partial)

`_handle_run_command` in `tools.py` calls `judge.approve()` and then
`executor.run()` but never calls `judge.record_outcome()`. The `/run` slash
command in `main.py` has the same pattern. By contrast, `_handle_run_code`
properly calls `record_outcome()` on both success and failure.

In the agent loop (`agent.py`), `record_outcome()` is called after every
`dispatch_tool()` — so tool calls from the LLM do get tracked. But direct
`/run` slash-command usage does not. This means:

- Trust evolution data for `run_command` from interactive use is incomplete.
- The "proven safe" auto-promotion mechanism has a blind spot for the most
  commonly used interactive tool.

**Fix:** Add `judge.record_outcome("run_command", command, "success"/"error")`
after `executor.run()` in both `_handle_run_command` (tools.py) and
`cmd_run` (main.py).

---

### P1-5: Double intent classification on HTTP `/chat` endpoint

**File:** [hal/server.py](../hal/server.py#L508),
[hal/bootstrap.py](../hal/bootstrap.py#L357)
**Investigation target:** F.1

The `/chat` handler calls `classifier.classify()` at line 508 to get the
intent label for the response metadata, then passes `classifier` to
`dispatch_intent()` which calls `classifier.classify()` again at line 357.
Each classification is an embedding call to Ollama (~30-50ms). Every HTTP
query pays this cost twice.

**Fix:** Pass the already-computed `(intent, confidence)` tuple to
`dispatch_intent()` instead of the classifier object, and have
`dispatch_intent()` accept `intent: str` directly.

---

### P1-6: `sanitize_query()` does not strip IPv6 private addresses

**File:** [hal/web.py](../hal/web.py#L20-L45) (approx.)
**Investigation target:** E.2

`sanitize_query()` strips IPv4 RFC1918 ranges, loopback, and Tailscale CGNAT
from user queries before sending them to Tavily. But IPv6 private ranges
are not stripped: `fe80::` (link-local), `fd00::` (ULA), `::1` (loopback),
and `fc00::` are all passed through to the external search API.

**Why it matters:** If a user asks about a local service and includes an
IPv6 address (e.g., "why can't I reach fd00::1 port 8000"), that private
address leaks to Tavily's servers.

**Fix:** Add an IPv6 regex pattern for link-local, ULA, and loopback ranges
to `sanitize_query()`.

---

### P1-7: `tracing.py` broad exception catch masks configuration bugs

**File:** [hal/tracing.py](../hal/tracing.py#L86) (approx.)
**Investigation target:** B.2

After the `ImportError` handler for optional OTel packages, a second
`except Exception as exc` catches all other failures and logs at INFO level.
This masks real configuration bugs (wrong endpoint format, auth failures,
SDK version incompatibilities) behind "Tracing disabled" at a non-alarming
log level.

**Fix:** Log at WARNING level for non-`ImportError` exceptions, and include
the exception class name in the message so the operator can distinguish
"package not installed" from "package broken."

---

### P1-8: `config.py` silently skips malformed `EXTRA_HOSTS` entries

**File:** [hal/config.py](../hal/config.py#L79) (approx.)

The `host_registry` property parses `EXTRA_HOSTS` (comma-separated
`name:user@ip` entries) but silently skips entries that don't match the
expected format. A typo like `laptop:jp192.168.5.20` (missing `@`) is
silently ignored — the host simply doesn't appear in the registry.

**Fix:** Log a WARNING for each malformed entry with the raw value, so the
operator can see the typo.

---

### P1-9: Host temp file briefly world-readable in sandbox execution

**File:** [hal/sandbox.py](../hal/sandbox.py#L170-L196) (approx.)
**Investigation target:** D.3

`execute_code()` writes the user's code to `/tmp/hal-sandbox-{uuid}.py` on
the host filesystem. Between file creation and the `finally` cleanup (which
deletes it), the file is readable by any process on the host with access to
`/tmp`. The default umask (typically 022) makes it world-readable.

**Mitigating factors:** The file exists briefly, the UUID is unpredictable,
and this is a single-user homelab. But defense-in-depth would use
`tempfile.NamedTemporaryFile` with explicit `mode=0o600`.

**Fix:** Use `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`
or `tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)`.

---

## P2 — Code Smells / Inconsistencies

### P2-1: `FALCO_LOG` defined inconsistently in two modules

**Files:** [hal/security.py](../hal/security.py#L30),
[hal/watchdog.py](../hal/watchdog.py#L39)
**Investigation target:** C.3

`security.py` uses `os.environ.get("FALCO_LOG_PATH", "/var/log/falco/events.json")`
— env-configurable. `watchdog.py` uses `Path("/var/log/falco/events.json")` —
hardcoded. If the operator sets `FALCO_LOG_PATH`, `security.py` respects it
but `watchdog.py` ignores it.

**Fix:** Have `watchdog.py` read the same env var, or import the constant
from `security.py`.

---

### P2-2: `HAL_CHAT_URL` hardcoded in `telegram.py`

**File:** [hal/telegram.py](../hal/telegram.py#L39)
**Investigation target:** C.1

`HAL_CHAT_URL = "http://127.0.0.1:8087/chat"` is a module-level literal. If
the server port changes (the `--port` flag on `server.py` supports this),
the Telegram bot silently posts to the wrong URL.

**Fix:** Read from an env var (`HAL_CHAT_URL`) with this as the default, or
derive from `Config`.

---

### P2-3: System prompt contains hardcoded port numbers and interface names

**File:** [hal/bootstrap.py](../hal/bootstrap.py#L50-L175)
**Investigation target:** C.4

While many values are derived from `Config` URLs (vLLM port, Ollama port,
Prometheus port, ntopng port), several are still literal:

- Pushgateway: `":9092"` (line ~89)
- Grafana: `":3001"` (line ~90)
- Cockpit: `":9090"` (line ~92)
- Tempo: `":4318/:3200"` (line ~91)
- Interface name: `"enp130s0"` (line ~97)

These survive a server migration unchanged even when the real ports differ.

**Fix:** Add `pushgateway_url`, `grafana_url`, `tempo_url` to `Config` and
derive ports from them, or accept this as intentional documentation (these
ports rarely change).

---

### P2-4: `TURN_WINDOW = 40` is a non-configurable module constant

**File:** [hal/memory.py](../hal/memory.py#L10) (approx.)
**Investigation target:** C.5

The context window size (how many turns are loaded from SQLite into LLM
context) is a bare integer constant. Changing it requires editing source
code.

**Fix:** Add `turn_window` to `Config` with default 40.

---

### P2-5: `llm.py` vestigial `"data" in locals()` guard

**File:** [hal/llm.py](../hal/llm.py#L130) (approx.)

Line ~130 has `usage = data.get("usage") if "data" in locals() else None`.
The `"data" in locals()` check is vestigial — if an exception occurred
before `data` was assigned, the function already returned via the
`except` clause's `raise`. At this point `data` is always defined.

**Fix:** Simplify to `usage = data.get("usage")`.

---

### P2-6: `trust_metrics.py` pattern drift risk with `judge.py`

**File:** [hal/trust_metrics.py](../hal/trust_metrics.py#L200-L250) (approx.)

`_extract_action_class()` in `trust_metrics.py` has its own destructive
command pattern list (a subset of Judge's `_CMD_RULES`). If new patterns
are added to the Judge, they must also be added here — but there's no
enforcement mechanism.

**Fix:** Import the pattern list from `judge.py`, or extract shared patterns
into a common module.

---

### P2-7: `healthcheck.py` derives Pushgateway/Grafana URLs by hardcoding ports

**File:** [hal/healthcheck.py](../hal/healthcheck.py#L210-L250) (approx.)
**Investigation target:** C.2

`check_pushgateway()` parses `config.prometheus_url` to get the hostname,
then constructs `http://{host}:9092`. `check_grafana()` does the same with
port 3001. If either service moves to a different port, the health checks
silently break.

**Fix:** Add `pushgateway_url` and `grafana_url` to `Config`, or accept this
as an intentional simplification given the stable homelab port assignments.

---

### P2-8: CORS `allow_origins=["*"]` in production server

**File:** [hal/server.py](../hal/server.py#L304)

The FastAPI CORS middleware allows all origins. This is appropriate for a
same-LAN homelab where the Web UI is served from the same origin, but it
means any website visited by a browser on the LAN could make authenticated
requests to `/chat` if it knows the bearer token.

**Fix (low priority):** Restrict to the server's own origin, or add an env
var for allowed origins.

---

### P2-9: `_handle_conversational` does not call `strip_tool_call_artifacts()`

**File:** [hal/bootstrap.py](../hal/bootstrap.py#L310-L330) (approx.)

`_handle_conversational()` takes the LLM response and writes it to history
without running it through `strip_tool_call_artifacts()` — the sanitizer
that removes hallucinated tool-call JSON from prose. The agent loop
(`agent.py`) and the HTTP handler (`server.py`) both apply this sanitizer.

**Why it matters:** If the LLM hallucinates a tool-call block in a
conversational response (rare but has happened before — see SESSION_FINDINGS
B1), it would be saved to history raw and re-injected into future context.

**Fix:** Apply `strip_tool_call_artifacts()` to the response before saving
to history.

---

### P2-10: `/postmortem` hardcodes `window_hours=24`

**File:** [hal/main.py](../hal/main.py#L179)

The `/postmortem` slash command calls `gather_postmortem_context()` with
`window_hours=24`. The ROADMAP says `/postmortem <desc> [--hours N]` with
default 2h, but the implementation uses 24h and does not parse `--hours`.

**Fix:** Parse `--hours N` from the description string, or accept 24h as
the intended default.

---

### P2-11: `watchdog.py` `_check_component_health` swallows all exceptions

**File:** [hal/watchdog.py](../hal/watchdog.py#L395-L420) (approx.)

`_check_component_health()` wraps the entire health check suite in
`try: ... except Exception: return None`. If the health check module has a
bug, the watchdog silently skips it — no log entry, no alert.

**Fix:** Log at WARNING level in the exception handler.

---

## Intentional Patterns (Not Findings)

These were investigated and confirmed as deliberate design choices:

| Pattern | File | Why it's intentional |
|---------|------|---------------------|
| `shell=True` in `SSHExecutor.run()` | executor.py | All commands go through Judge first; `noqa: S602` documented |
| `shell=True` in `collect.py:_run()` | collect.py | All callers pass hardcoded command strings; `noqa: S602` documented |
| `subprocess.run` without full path | watchdog.py, healthcheck.py | Known binaries (`docker`, `timedatectl`, `tail`); `noqa: S607` documented |
| Empty tools on final iteration | agent.py | Forces text response; prevents infinite loop (documented in ARCHITECTURE.md) |
| Dedup injection message | agent.py | Breaks tool-call loops; documented guard rail |
| `_CONTROL_TOKEN_RE` stripping | (removed in refactor) | Was a band-aid; now handled by `strip_tool_call_artifacts()` |
| `except Exception` in health checks | healthcheck.py | Each check is isolated; failure in one must not crash the suite |
| `except Exception` in `IntentClassifier._build()` | intent.py | Graceful degradation to always-agentic routing |
| `sys.exit(1)` in `setup_clients()` | bootstrap.py | CLI cannot function without LLM backends; server catches and retries |
| `_send_ntfy_simple` returning False on failure | notify.py | Caller checks return value; not truly silent |
| KB connection-per-operation (no pool) | knowledge.py | Acceptable for current single-user homelab load |

---

## Known Debt Items — Status Verification

Items from `SESSION_FINDINGS.md` and `ROADMAP.md`, verified against current
code:

| ID | Status | Notes |
|----|--------|-------|
| P1 (control token stripping) | **Resolved** | `_CONTROL_TOKEN_RE` removed; `strip_tool_call_artifacts()` in `sanitize.py` handles this |
| P2 (loop-breaking message) | **Active, intentional** | Still in agent.py; documented guard rail |
| P3 (no-tools on final iteration) | **Active, intentional** | Still in agent.py; prevents unbounded loops |
| P4 (missing tool_call_id) | **Resolved** | Both tool result paths include `tool_call_id` |
| P5 (Judge `_llm_reason` prompt) | **Still pending** | `_llm_reason()` still uses `chat()` without explicit no-tools instruction; low risk since `chat()` doesn't pass tool schema |
| RC1 (unreliable tool calls) | **Resolved** | Switched to vLLM + Qwen2.5-32B-Instruct-AWQ; eval shows 100% |
| RC2 (model identity override) | **Mitigated** | Stronger system prompt identity assertions; eval hal_identity=100% |
| RC3 (history poison propagation) | **Resolved** | Poison filter in memory.py + 30-day pruning |
| RC4 (no conversational category) | **Resolved** | Conversational category with 30 examples in intent.py |
| RC5 (unconditional KB seeding) | **Resolved** | Threshold raised to 0.75; only strong matches seed |
| ROADMAP C1 (system prompt template) | **Partially done** | Ports derived from config; hardware/interface names still literal |
| ROADMAP C2 (externalize Judge patterns) | **Not started** | `_CMD_RULES`, `_SENSITIVE_PATHS` still Python literals |
| ROADMAP C3 (hardcoded config defaults) | **Done** | `_required_env()` raises RuntimeError on missing values |
| ROADMAP C4 (pluggable harvest) | **Done** | Glob patterns, per-collector try/except, configurable inputs |

---

## Summary

| Severity | Count | Key themes |
|----------|-------|------------|
| **P0** | 4 | Sandbox hardening (3), SSRF TOCTOU (1) |
| **P1** | 9 | Silent error swallowing (3), missing audit trail (2), double work (1), privacy leak (1), config fragility (2) |
| **P2** | 11 | Hardcoded values (4), inconsistencies (3), code smells (4) |

**Recommended priority order:**

1. P0-2 + P0-3 (sandbox `--cap-drop` + `--user`) — single commit, high impact
2. P0-1 (sandbox cleanup Judge gating) — single line change
3. P1-1 (Prometheus logging) — quick win, prevents future debugging pain
4. P1-4 (`run_command` outcome tracking) — completes trust evolution coverage
5. P1-5 (double classification) — performance fix, straightforward refactor
6. P0-4 (SSRF TOCTOU) — harder to fix correctly; tier-1 gate mitigates risk
7. Everything else in P1/P2 order
