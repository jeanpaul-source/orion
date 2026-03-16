# Phase 1 Audit Findings

> Living document — updated as findings are verified, fixed, or reclassified.
>
> Last verified: 2026-03-15 by coordinator chat (direct code reads with tool-call evidence).
> 1A/1E/1F re-verified: 2026-03-15 — line numbers refreshed, F-10/25 and F-8 corrected.
> 1B re-verified: 2026-03-15 — all 7 findings code-checked against actual source. F-39
> dropped (double-classify claim wrong); replaced by F-90 (conversational routing
> disabled in HTTP). F-53 downgraded LOW; 4 new findings added (F-90–F-93).
> 1C re-verified: 2026-03-15 — all 9 original findings code-checked against actual
> source; line numbers refreshed. F-59 restored; 2 new findings added (F-94–F-95).
> 1D re-verified: 2026-03-15 — all 14 original findings code-checked against actual
> source; line numbers corrected (8 findings had wrong lines). F-70 and F-78 confirmed
> dropped. 6 new findings added (F-96–F-101). Total 1D: 20 findings.
> 1E re-verified: 2026-03-15 — all 5 prior findings code-checked (line numbers
> corrected on F-86, F-87, F-88). 10 new findings added (F-102–F-111) from full
> audit of prometheus.py, tracing.py, trust_metrics.py, logging_utils.py,
> healthcheck.py, watchdog.py, notify.py, falco_noise.py. Total 1E: 15 findings.
> Every finding below has a file + line citation confirming it exists in the codebase.

## How to read this file

Each finding has:

- **ID**: Stable identifier (F-NNN). Never reused, even if dropped.
- **Severity**: HIGH (data loss, auth bypass, container escape) /
  MED (defense gap, reliability risk, config fragility) /
  LOW (code quality, doc drift, minor hardening)
- **Evidence**: File path + line number(s) where the issue was confirmed.
- **Status**: `open` (confirmed, not fixed) | `fixed` (PR merged) | `dropped` (invalid after code read)
- **Description**: What's wrong and why it matters.

## Summary

| Area | Scope | HIGH | MED | LOW | Total |
| --- | --- | --- | --- | --- | --- |
| 1A | Safety & Security | 2 | 4 | 6 | 12 |
| 1B | Control-plane & Routing | 0 | 5 | 6 | 11 |
| 1C | Knowledge & Retrieval | 2 | 4 | 6 | 12 |
| 1D | Runtime & Deployment | 1 | 5 | 14 | 20 |
| 1E | Observability & Trust | 2 | 6 | 7 | 15 |
| 1F | Docs & Prompt Drift | 0 | 2 | 0 | 2 |
| **Total** | | **7** | **26** | **39** | **72** |

Dropped: F-21, F-32, F-39, F-49, F-70, F-78 (6 findings invalidated by code read).
F-74 merged into F-47 (duplicate).
Resolved: F-71 (watchdog interval corrected in SUMMARY.md).

---

## 1A — Safety & Security

### F-14 · HIGH · `open` · Verified 2026-03-15

**Missing `--cap-drop ALL` in sandbox Docker flags**
`hal/sandbox.py` L70–100 (`_build_docker_command`): The Docker run command (flags at
L92–99) includes `--network none`, `--memory`, `--read-only`, `--pids-limit`, and
`--tmpfs`, but does not include `--cap-drop ALL`. The container inherits the default
Docker capability set, which includes `CAP_NET_RAW`, `CAP_SYS_CHROOT`, and others
that are unnecessary for running a Python script.

### F-15 · HIGH · `open` · Verified 2026-03-15

**Missing `--user` runtime flag in sandbox**
`hal/sandbox.py` L70–100 (`_build_docker_command`, flags at L92–99): No `--user`
flag. The process inside the sandbox runs as whatever user is the default in the
image (root in `python:3.12-slim` unless the `USER` directive in
`Dockerfile.sandbox` changes it). `Dockerfile.sandbox` L9 sets `USER sandbox`, so
the image default is non-root — but the `docker run` command does not enforce this,
meaning a modified image or a `--user root` injection in a future change would
silently escalate.

### F-1/17 · MED · `open` · Verified 2026-03-15

**Sandbox cleanup `rm -f` bypasses Judge**
`hal/sandbox.py` L179–183 (finally block): After sandbox execution completes, the
temp file is cleaned up with `executor.run(f"rm -f {shlex.quote(host_code_path)}")`
at L183. This is a direct `executor.run()` call — it bypasses `judge.approve()`
entirely. `rm -rf` (which subsumes `rm -f`) is a tier-3 pattern in `judge.py` L37.

Risk is low in practice (the file was just created by the same function, path is
UUID-randomized and shlex-quoted), but it establishes a precedent of bypassing the
Judge for cleanup operations.

### F-8 · MED · `open` · Verified 2026-03-15

**Bash herestring `<<<` not in evasion patterns**
`hal/judge.py` L301 (`_EVASION_PATTERNS`) and L321 (`_COMMAND_SEPARATORS`): The
evasion detector catches `$()`, backticks, `eval`, `exec`, `base64 -d | sh` (L309),
process substitution `<()` / `>()`, and hex/octal escapes. It does **not** catch bash
herestrings (`<<<`), which can feed arbitrary input to commands.

`base64 -d <<< <payload>` alone just decodes to stdout (tier 2 — `base64` is not in
`_SAFE_FIRST_TOKENS` so it defaults to unknown-deny). The real gap: `<<<` is an
undetected input redirection mechanism. If combined with a safe-token command
(`cat <<< "$(malicious)"`), the `$()` inside would still be caught — but the `<<<`
itself is invisible to the evasion detector.

### F-10/25 · MED · `open` · Verified 2026-03-15

**`env` in safe first-tokens allows unknown binary execution at tier 0**
`hal/judge.py` L140 (`_SAFE_FIRST_TOKENS`), `"env"` at L192: `env` is in the
safe-command allowlist. `env` can prefix any command — but **known-dangerous patterns
ARE caught**: `env /usr/bin/rm -rf /` is correctly classified as tier 3 because
`classify_command()` (L540–542) checks `_CMD_RULES` substring patterns against the
full command string *before* splitting or checking safe tokens.

The real gap: `env some_unknown_binary` gets tier 0 because (1) no `_CMD_RULES`
pattern matches, (2) `_classify_single_command` sees `env` as the first token and
calls `_is_safe_command` (L516) which returns True. The unknown binary runs unvetted.
The `_SAFE_COMPOUND` table does not cover `env` + second-token patterns.

### F-18 · MED · `open` · Verified 2026-03-15

**DNS-rebinding TOCTOU in `fetch_url()`**
`hal/web.py` L136–190 (`_validate_url`): DNS is resolved and checked against private
IP ranges *before* the HTTP request. A DNS rebinding attack could return a public IP
during validation, then switch to 127.0.0.1 for the actual request.

Mitigated by: post-redirect re-validation at L226–227 (`if resp.url != url:
_validate_url(resp.url)`). This closes the redirect vector but not the initial-request
rebinding window.

### F-2 · LOW · `open` · Verified 2026-03-15

**REPL slash commands skip `record_outcome()`**
`hal/main.py` L91 (`cmd_run`): The `/run` command calls `judge.approve()` and
`executor.run()` but never calls `judge.record_outcome()`. Same applies to `/read`
(L107), `/ls` (L118), `/write` (L129). The agent loop (`hal/agent.py` L284–289) does
call `record_outcome()`. This means slash-command executions don't contribute to the
trust-evolution data that the Judge uses to auto-promote proven-safe commands.

### F-9 · LOW · `open` · Verified 2026-03-15

**`python -c` classified as tier 2, not tier 3**
`hal/judge.py` L78 (`_CMD_RULES` tier 2): `python -c` and `python3 -c` are in the
tier-2 (config change) list. Tier 2 requires explain+approve, but a malicious
`python3 -c "import os; os.system('rm -rf /')"` could be destructive. The risk is
mitigated by the `run_code` sandbox tool existing for legitimate code execution.

### F-11 · LOW · `open` · Verified 2026-03-15

**Background `&` not handled by command splitting**
`hal/judge.py` L321 (`_COMMAND_SEPARATORS`): The regex splits on `;`, `&&`, `||`, `|`,
and `\n`, but not on `&` (shell background operator). `safe_cmd & unknown_cmd` is
evaluated as a single command. Dangerous patterns in `_CMD_RULES` still match the full
string, so `safe & rm -rf /` is caught — but `safe & moderately_risky` could get a
lower tier than expected.

### F-16 · LOW · `open` · Verified 2026-03-15

**Sandbox temp file world-readable**
`hal/sandbox.py` L139: Temp files are written to `/tmp/hal-sandbox-{uuid}.py` via
`executor.write()` (L143). The file inherits the default umask (typically 0022 →
permissions 0644), making the code visible to all users on the host. The file exists
only briefly (created, mounted, then deleted in the finally block at L179–183), but
during execution the code is readable by any process.

### F-19 · LOW · `open` · Verified 2026-03-15

**IPv6 private addresses not stripped from search queries**
`hal/web.py` L28–36 (`_PRIVATE_IP_RE`): The sanitizer regex only matches IPv4 private
ranges (10.x, 172.16-31.x, 192.168.x, 127.x, 100.x). IPv6 private addresses
(`fe80::`, `fd00::`, `::1`) are not stripped. If a query contains an IPv6 address, it
would be sent to the Tavily search API. Note: URL SSRF validation (`_is_private_ip` at
L120) does handle IPv6 via `ipaddress.ip_address()` — this gap is query-sanitization
only.

### F-22 · LOW · `open` · Verified 2026-03-15

**15+ tools exposed to LLM every turn**
`hal/tools.py` L397+ (`TOOL_REGISTRY`): 17 registered tools, 15 always-enabled.
`hal/agent.py` L122 (`available_tools = get_tools(…)`): All enabled tools are sent in
every LLM call (except the final iteration, L196). This inflates the system prompt and
can cause the model to hallucinate tool calls for simple questions. Not a bug — a
design trade-off — but worth revisiting if prompt token budget becomes a concern.

---

## 1B — Control-plane & Routing

### F-90 · MED · `open` · Verified 2026-03-15

**Conversational routing disabled in HTTP/Telegram path**
`hal/server.py` L530 (`dispatch_intent(...)` call inside `_run()`): The call does
**not** pass `classifier=` as a keyword argument. `dispatch_intent()` signature at
`hal/bootstrap.py` L335 defaults `classifier` to `None`. At L358:
`if classifier is not None:` — this branch is skipped, so **all** HTTP queries route
straight to `run_agent()` (full tool loop, KB + Prometheus pre-seed).

The REPL path (`hal/main.py` L444) correctly passes `classifier=classifier`.

Consequence: greetings ("hi", "thanks") over HTTP/Telegram go through the full
agentic loop with 15+ tools. This wastes an LLM round-trip with tool definitions,
incurs a KB search and Prometheus call, and produces heavier responses than the
conversational fast-path. The `classify()` call at `server.py` L508 still runs and
the intent label is returned in the `ChatResponse`, but it has no routing effect —
it's metadata-only.

Originally reported as F-39 ("double classify") — that claim was incorrect. There is
exactly one `classify()` call per HTTP request, at L508, for metadata only. The real
bug is that the classifier is not wired into routing.

Tested: `test_integration.py` `TestDispatchIntentRouting` tests the REPL path
(passes `classifier=FakeClassifier(...)`). No test exercises the server path's
omission of `classifier=`.

### F-29 · MED · `open` · Verified 2026-03-15

**`sys.exit(1)` used as control flow in bootstrap**
`hal/bootstrap.py` L218, L229, L239, L268, L278 (`_connect` and `setup_clients`):
Five `sys.exit(1)` calls — two for localhost unreachable, one for lab-host-is-local
unreachable, one for tunnel failure, one each for vLLM-not-ready and Ollama-not-ready.
`hal/server.py` L269-280 (`lifespan`): The server catches `SystemExit` to enter
degraded mode and spawns `_retry_init()` as an async background task (L280).
`hal/main.py` L305: `setup_clients(config)` is called with no `SystemExit` handler —
HAL REPL exits immediately. This is correct for interactive use but produces the
cryptic message from `sys.exit(1)` rather than a user-friendly error.

Using `SystemExit` for expected control flow is fragile — a bare `except Exception`
anywhere in the call stack would swallow it silently (Python 3 `Exception` does not
catch `SystemExit`, but `except BaseException` would). Risk is moderate because
`SystemExit` is a `BaseException`, not an `Exception`, so `except Exception:` blocks
do NOT catch it. The actual risk is a future developer adding `except BaseException:`.

### F-45 · MED · `open` · Verified 2026-03-15

**No LLM retry logic**
`hal/llm.py` L97 and L155 (`chat_with_tools` and `chat`): Each method makes a
single `requests.post(…, timeout=120)` call. If the request fails (timeout at 120s,
connection error, HTTP 500), the exception propagates via `raise` at L113/L169.
There is no retry, backoff, or circuit breaker in the LLM client.

The agent loop in `hal/agent.py` L205–216 catches the exception, logs it, records
metrics, and returns `AgentResult(response=err)` — the turn fails but history is not
corrupted (correct H-1 contract). The conversational handler in `hal/bootstrap.py`
L310 has the same pattern.

A transient vLLM hiccup (GPU memory pressure, brief OOM) causes an immediate turn
failure with no retry. For a 120-second timeout, one could argue a retry is
undesirable (the user already waited 2 minutes), but a single retry with a shorter
initial timeout (e.g., 30s + 120s fallback) would catch transient errors.

### F-47 · MED · `open` · Verified 2026-03-15

**Config bare int/float casts with no validation**
`hal/config.py` L108, L122–125, L127, L129–138 (`load()`): Environment variables
are cast with bare `int()` and `float()` calls:

- `int()`: L108 (`TELEGRAM_ALLOWED_USER_ID`), L127 (`SANDBOX_TIMEOUT`)
- `float()`: L122 (`LLM_TEMPERATURE`), L123 (`LLM_TOP_P`), L124 (`LLM_MIN_P`),
  L125 (`LLM_REPETITION_PENALTY`), L129-138 (four watchdog rate thresholds)

A malformed value (e.g., `LLM_TEMPERATURE=high`) raises `ValueError` at startup
with a traceback but no explanatory message pointing to the env var name.
No range validation (e.g., `temperature ∈ [0, 2]`, `sandbox_timeout > 0`).

Test coverage: `tests/test_config.py` tests required vars, defaults, and overrides
but does NOT test malformed values — no test for `LLM_TEMPERATURE=invalid`.

### F-53 · LOW · `open` · Verified 2026-03-15

**IntentClassifier not rebuilt in REPL after Ollama failure at startup**
`hal/intent.py` L179–195 (`__init__` and `_build`): If Ollama is unreachable when
`_build()` runs at L180, `_ready` is set to `False` (L195) and `classify()` returns
`("agentic", 0.0)` for all queries (L204–208).

Server path: **correctly handled.** `_retry_init()` calls `_populate_state()` at
`hal/server.py` L200, which constructs `IntentClassifier(embed)` at L149 — a fresh
classifier with a fresh `_build()` call. If Ollama is up by retry time, classification
works.

REPL path: `hal/main.py` L312 builds the classifier once. If Ollama was down at that
moment, the classifier stays permanently degraded — all queries route to `run_agent()`
for the session's lifetime. The REPL would need to be restarted to pick up Ollama.

Previously rated MED. Downgraded to LOW because: (1) if Ollama is down at REPL start,
`setup_clients()` already calls `sys.exit(1)` at L278 — the REPL never reaches L312.
The only way to hit this bug is if Ollama's HTTP port is open (passing `embed.ping()`)
but the embed endpoint fails during `_build()` — a narrow window. (2) The
consequence (all-agentic routing) is the safe fallback.

### F-42 · LOW · `open` · Verified 2026-03-15

**`prune_old_turns()` not called in server path**
`hal/main.py` L313: `mem.prune_old_turns()` runs at REPL startup. The HTTP server
(`hal/server.py`) creates a fresh `MemoryStore` per request (L513) but never calls
`prune_old_turns()`. Old sessions accumulate indefinitely in the server path.

Mitigated if operator occasionally starts a REPL session (triggers the prune). The
impact is slow: with a single user and ~40 turns per session, accumulation rate is
tens of KB per day. Visible impact would take months.

### F-31 · LOW · `open` · Verified 2026-03-15

**SQLite corruption requires manual deletion**
`hal/memory.py` L35–40 (`_connect`): Creates DB directory (L36), opens connection
(L37), sets `PRAGMA journal_mode=WAL` (L39), calls `_init()` (L40). `_init()` at
L44–57 runs `CREATE TABLE IF NOT EXISTS` via `executescript()` (L45–56), then
`conn.commit()` (L57 — redundant since `executescript()` auto-commits).

If the DB file is corrupted (e.g., 0-byte file from crash during first write),
`sqlite3.connect()` opens it but subsequent operations raise `DatabaseError`.
No corruption detection or automatic recovery.
Documented workaround: `rm ~/.orion/memory.db` (OPERATIONS.md L372–378).

### F-91 · LOW · `open` · Verified 2026-03-15

**Dead `"data" in locals()` guard in llm.py**
`hal/llm.py` L124 (`chat_with_tools`): Token accounting line:
`usage = data.get("usage") if "data" in locals() else None`. The `"data" in locals()`
check is dead code — `data` is always defined when execution reaches L124 because the
only path to L124 is through the success branch of the try block (L93–105) where
`data = r.json()` is assigned at L105. The error path (L106–113) re-raises, so
execution never reaches L124 on failure.

Contrast with L172 in `chat()` which uses `data.get("usage")` directly — no
`locals()` guard. Both are correct; L124 just has unnecessary defensive code.

### F-92 · LOW · `open` · Verified 2026-03-15

**Server session default picks up unrelated sessions**
`hal/server.py` L522 (`_run` inside `chat()`): When `req.session_id` is `None`,
`mem.last_session_id()` returns the globally most-recent session regardless of
origin. If the Telegram bot created a `tg-12345` session and a Web UI user
subsequently hits `/chat` without a session ID, the Web UI user would resume the
Telegram session's history.

Mitigated by: Telegram bot always provides `session_id` (format `tg-<chat_id>`).
The Web UI likely stores and sends session_id after the first response.
Still a silent correctness issue for any client that omits session_id.

### F-93 · LOW · `open` · Verified 2026-03-15

**Malformed `EXTRA_HOSTS` entries silently ignored**
`hal/config.py` L75–82 (`host_registry` property): Entries in `EXTRA_HOSTS` that don't
match the `name:user@host` format are silently skipped via `continue` at L78, L80, L82.
No warning is logged. If an operator misspells an entry (e.g., `laptop:jp192.168.5.20`
missing `@`), the host silently disappears from the registry. Tested in
`tests/test_config.py` L144–150 (`test_host_registry_skips_malformed`).

---

## 1C — Knowledge & Retrieval

> 1C verified: 2026-03-15 — all 9 original findings code-checked against actual
> source; line numbers refreshed. F-59 restored (was in initial audit but never
> committed to this file). Two new findings added (F-94, F-95). Total: 12 findings.

### F-56 · HIGH · `open` · Verified 2026-03-15

**Non-atomic clear-then-insert in harvest**
`harvest/ingest.py` L201–202 (`ingest()`): The function calls `clear_lab_docs(conn)`
(L201) and `clear_ground_truth(conn)` (L202) *before* re-ingesting new documents.
Each clear function commits independently — `clear_lab_docs` at L73, `clear_ground_truth`
at L101 — while the final insert commit is at L271. Three separate `conn.commit()` calls
with no single transaction boundary.

If the process crashes between the clear commits and the final insert commit (L271), the
KB is left with zero lab-state and zero ground-truth documents. Reference docs use
incremental mode and survive, but all harvested lab state is lost until the next
successful harvest run (up to 24 hours).

Test gap: no test covers `ingest()` transaction behavior — the existing tests cover
`_chunk()`, `_doc()`, and snapshot parsers, but not the ingestion function itself.

### F-65 · HIGH · `open` · Verified 2026-03-15

**Partial harvest clears all lab-state rows**
`harvest/ingest.py` L65–73 (`clear_lab_docs`): Deletes ALL rows where
`category = ANY(...)` for `{'lab-infrastructure', 'lab-state'}` (L69) then commits
(L73), even if only one collector source failed.

Two separate failure paths lead to data loss:

1. **Collector failure:** `collect_all()` (`harvest/collect.py` L420–438) wraps each
   collector in try/except and prints a warning, but continues. If
   `collect_docker_containers()` fails (Docker daemon down), it returns zero docs for
   containers. `ingest()` then calls `clear_lab_docs()` (deletes ALL lab rows including
   containers from the *previous* successful harvest) and only inserts the partial set.
   Container docs are gone until the next full harvest — up to 24 hours.
2. **Embedding failure:** Within `ingest()` L237–247, if `llm.embed()` raises for some
   chunks, those chunks are lost but already-cleared rows are not restored.

### F-55 · MED · `open` · Verified 2026-03-15

**No ANN index on embeddings column**
`hal/knowledge.py` L88–94 (`search()`): The query uses `ORDER BY embedding <=> %s`
(pgvector cosine distance operator) with `LIMIT`. No ANN index creation (IVFFlat or
HNSW) exists anywhere in the codebase — not in `ingest.py`, not in `knowledge.py`,
not in any migration script. Without an index, pgvector performs a sequential scan
over all rows on every search call. Performance degrades linearly with row count.

Whether an index was created manually via `psql` is unknown — see
"Unknowns requiring runtime verification" below.

### F-57 · MED · `open` · Verified 2026-03-15

**`STATIC_DOCS_ROOT` hardcoded in ingest.py, ignoring config**
Three independent definitions of the same path:

- `harvest/ingest.py` L44: `STATIC_DOCS_ROOT = "/data/orion/orion-data/documents/raw"`
- `harvest/collect.py` L353: `_STATIC_DOCS_ROOT = Path("/data/orion/orion-data/documents/raw")`
- `hal/config.py` L112: `os.getenv("STATIC_DOCS_ROOT", "/data/orion/orion-data/documents/raw")`

`collect_static_docs()` accepts a `root` parameter (collect.py L356) and `collect_all()`
passes `Path(static_docs_root)` from config (L433). So collection respects the env var.
But `clear_static_docs()` (ingest.py L86) and `_clean_orphan_static_docs()` (ingest.py
L137) always use the hardcoded `STATIC_DOCS_ROOT` from ingest.py. If the env var is
changed, the cleanup functions still target the old path — leaving orphan rows and
failing to clean new-path docs.

### F-60 · MED · `open` · Verified 2026-03-15

**Shell failures produce stub documents in KB**
`harvest/collect.py` L141–209 (`collect_system_state`): Four sub-collectors build docs
unconditionally regardless of whether `_run()` returned empty output:

- Disk (L147–157): `disk = _run(…)` → doc appended at L150 even if `disk` is `""`
- Memory (L161–179): `mem = _run("free -h")` → doc appended at L172 even if `mem` is `""`
- Ports (L183–191): `ports = _run(…)` → doc appended at L184 even if `ports` is `""`
- Services (L195–207): `services = _run(…)` → doc appended at L199 even if `services` is `""`

In contrast, Ollama models (L210–223) correctly checks `if models:` before appending.
Docker containers (`collect_docker_containers` L86) checks `if not raw: return []`.

`_run()` (L12–14) does not check `result.returncode`. A failed command returns empty
stdout. The KB ends up with documents whose content is just a header line with no data
(e.g., `"Disk usage (as of 2026-03-15 12:00):\n"`), which pollute search results
without providing useful information.

### F-64 · MED · `open` · Verified 2026-03-15

**`search()` has no pgvector error handling**
`hal/knowledge.py` L51–95 (`search()`): `self._connect()` (L57) calls
`psycopg2.connect(self.dsn)` (L42) then `register_vector(conn)` (L43). The query
execution (L88–94) and result parsing have no try/except. A connection failure raises
`psycopg2.OperationalError` whose message typically includes the full DSN with password.

Callers:

- Agent loop (`hal/agent.py` L132–148): catches `Exception` generically — the error
  message (with DSN) ends up in trace attributes and step logs but is not returned to
  the user.
- HTTP `/kb/search` (`hal/server.py` L436–459): no try/except around `kb.search()` —
  exception propagates to FastAPI's 500 handler. See F-61.
- `categories()` (L118–129) and `remember()` (L131–170): same pattern, no error handling.

### F-59 · LOW · `open` · Verified 2026-03-15

**No embedding model version stored with vectors**
`harvest/ingest.py` L241: embedding is generated via `llm.embed(chunk)` where `llm`
is an `OllamaClient` whose model comes from `config.embed_model` (default:
`nomic-embed-text:latest`, set in `hal/config.py` L100). Query-time embedding uses
the same `config.embed_model` via `hal/server.py` and `hal/main.py`. Both paths read
from the `EMBED_MODEL` env var, so they agree — as long as the env var hasn't changed
between the last harvest and the current query.

No model identifier is stored in the `documents` table alongside the embedding vector.
If `EMBED_MODEL` is changed in `.env` and HAL is restarted without re-running harvest,
the existing embeddings (old model's vector space) and query embeddings (new model's
vector space) are incompatible. Search quality degrades silently with no detection or
warning mechanism. The upsert in `ingest.py` L159–179 stores `content_hash` in
metadata but not the model name or version.

### F-61 · LOW · `open` · Verified 2026-03-15

**`/kb/search` endpoint leaks DSN in server logs on error**
`hal/server.py` L436–459 (`kb_search`): The `_run()` closure (L457) calls
`kb.search(q, ...)` with no try/except. If pgvector is unreachable,
`psycopg2.OperationalError` (containing the DSN with password) propagates through
`asyncio.to_thread()` to FastAPI's default exception handler. FastAPI returns a
generic HTTP 500 to the client (no DSN in the response body), but uvicorn logs the
full traceback with DSN to stderr.

Same pattern affects `/kb/categories` (L421–433) and `/kb/remember` (L462–478).

### F-62 · LOW · `open` · Verified 2026-03-15

**`ollama_host` interpolated unsanitized in shell command**
`harvest/collect.py` L211: `ollama_host` is interpolated directly into an f-string
shell command: `f"curl -s {ollama_host}/api/tags | python3 -c ..."` passed to `_run()`
which uses `shell=True` (L13). The `# noqa: S602` comment at L13 claims "all callers
pass hardcoded command strings, never user input" — this is inaccurate for the L211
call where `ollama_host` comes from `config.ollama_host` (env var `OLLAMA_HOST`).

Not exploitable from external input (env var is operator-controlled), but violates the
principle of parameterized commands. If `OLLAMA_HOST` contained shell metacharacters
(e.g., `http://host;rm -rf /`), they would be interpreted by the shell.

### F-63 · LOW · `open` · Verified 2026-03-15

**`harvest_snapshot.json` git-tracked but runtime-generated**
`knowledge/harvest_snapshot.json` is checked into git (confirmed via `git ls-files`)
and is NOT in `.gitignore`. It is written by the harvest pipeline at runtime
(`harvest/main.py` L80–81, `harvest/snapshot.py` L99 `write_snapshot()`). Changes
to the file after each harvest create noisy git diffs.

Intentional design: the file is committed so `git diff HEAD@{date}` can answer
"what changed since Tuesday?" (documented in `harvest/snapshot.py` L1–8 module
docstring). However, nothing in the codebase reads `harvest_snapshot.json` at
runtime — it is purely informational for human/git-diff inspection. If stale or
missing, no runtime impact.

### F-94 · LOW · `open` · Verified 2026-03-15

**New connection opened per KB operation — no connection pooling**
`hal/knowledge.py` L41–43 (`_connect`): Every call to `search()` (L57), `categories()`
(L121), and `remember()` (L142) creates a new `psycopg2.connect()` + `register_vector()`
connection, uses it, then closes it in a finally block (L95, L129, L170). No connection
pooling or reuse.

At current usage (single user, a few queries per minute), the overhead is ~5–20ms per
connection. Under higher load (multiple Telegram + web requests), this could exhaust
pgvector's `max_connections` (default: 100 in PostgreSQL). Each connection also pays
TCP handshake + pgvector extension registration overhead.

### F-95 · LOW · `open` · Verified 2026-03-15

**`_run()` in collect.py does not check command exit codes**
`harvest/collect.py` L12–14 (`_run()`): Returns `result.stdout.strip()` without
checking `result.returncode`. A command that fails with a non-zero exit code (e.g.,
`df` when a mount is stale, `ss` permission denied) returns empty or partial stdout
silently. The caller has no way to distinguish "command succeeded with empty output"
from "command failed."

Additionally, `_run()` does not handle `subprocess.TimeoutExpired` (the `timeout=15`
parameter at L13 raises `TimeoutExpired` on timeout). A hung command propagates
the exception to the per-collector try/except in `collect_all()` (L427), which
prints a warning and drops that collector's entire output.

Distinct from F-60: F-60 covers the *consequence* (stub docs in KB); this finding
covers the *root cause* (no exit code check in the shell helper).

---

## 1D — Runtime & Deployment

> 1D verified: 2026-03-15 — all 14 original findings code-checked against actual
> source; line numbers corrected. F-70 and F-78 remain correctly dropped (resource
> limits confirmed at docker-compose.yml L44–48; lock files confirmed via
> `git ls-files`). Six new findings added (F-96–F-101). Total: 20 findings.

### F-85 · HIGH · `open` · Verified 2026-03-15

**`HAL_WEB_TOKEN` defaults to empty — auth silently disabled on LAN**
`hal/config.py` L119: `hal_web_token=os.getenv("HAL_WEB_TOKEN", "")`.
`hal/server.py` L328–340 (`require_auth`): When token is empty, L334 returns
immediately — all `Depends(require_auth)` endpoints become unauthenticated.
Combined with F-69 (0.0.0.0 binding), the `/chat` endpoint accepts
unauthenticated requests from any device on the LAN.
`docker-compose.yml` L20: `"8087:8087"` (Docker defaults to 0.0.0.0 when no
bind address is specified).

### F-67 · MED · `open` · Verified 2026-03-15

**Dockerfile base image uses floating tag**
`Dockerfile` L2: `FROM python:3.12-slim`. Not pinned to a digest
(`python:3.12-slim@sha256:...`). A supply-chain attack on the upstream image would
silently affect the next build. CI rebuilds on every merge to `main`, so a compromised
upstream tag propagates automatically.

### F-69 · MED · `open` · Verified 2026-03-15

**docker-compose binds to all interfaces**
`docker-compose.yml` L20: `ports: ["8087:8087"]`. Without a `127.0.0.1:` prefix,
Docker binds to `0.0.0.0` — HAL's HTTP server is reachable from any device on the
LAN. Unauthenticated endpoints (`GET /`, `/static/*`, `/health`, `/kb/categories`)
are accessible without a token. Combined with F-85, `/chat` is also unauthenticated
when `HAL_WEB_TOKEN` is unset.

### F-83 · MED · `open` · Verified 2026-03-15

**Dockerfile.sandbox also uses floating base tag**
`Dockerfile.sandbox` L14: `FROM python:3.12-slim`. Same supply-chain risk as F-67,
but for the sandbox image that runs untrusted user code — a compromised base image
would have direct access to any code the LLM generates.

### F-100 · MED · `open` · Verified 2026-03-15

**Dockerfile installs from `requirements.txt` (loose) instead of lock file**
`Dockerfile` L18–19: `COPY requirements.txt .` / `RUN pip install ... -r requirements.txt`.
The lock file `requirements.lock` exists (991 lines, with `--generate-hashes` for hash
verification) and is git-tracked, but the Dockerfile uses `requirements.txt` which
specifies only `>=` lower bounds (19 entries, zero `==` pins). Two builds at different
times can resolve to different transitive dependency versions.

Compare: `Makefile` L49 (`dev-setup`) correctly uses `pip-sync requirements.lock`.
The Docker image — the production artifact — does not.

### F-101 · MED · `open` · Verified 2026-03-15

**`supervisor` installed unpinned and outside lock file**
`Dockerfile` L22: `RUN pip install --no-cache-dir supervisor`. The `supervisor`
package is not in `requirements.txt`, not in `requirements.lock`, and has no version
constraint or hash verification. Supervisord runs as PID 1 inside the container
(`ops/supervisord.conf` L3: `nodaemon=true`), managing the HTTP server and Telegram
bot. A compromised `supervisor` package on PyPI would gain full control of the
container on the next image build.

### F-68 · LOW · `open` · Verified 2026-03-15

**Dockerfile lacks multi-stage build — gcc in production image**
`Dockerfile` L5–9: `apt-get install -y --no-install-recommends openssh-client gcc
libpq-dev`. `gcc` (L7) and `libpq-dev` (L8) are build-time dependencies needed to
compile the `psycopg2` C extension. They remain in the final image because there is
no multi-stage build. A builder stage would shed the compiler toolchain (~200 MB)
and reduce attack surface in the runtime image.

### F-72 · LOW · `open` · Verified 2026-03-15

**Shadow config: 8 env vars bypass `config.py`**
The following env vars are loaded via `os.getenv()` / `os.environ.get()` directly in
their respective modules, not routed through `hal/config.py`:

- `PROM_PUSHGATEWAY` — `hal/prometheus.py` L262
- `HAL_INSTANCE` — `hal/prometheus.py` L283
- `OTLP_ENDPOINT` — `hal/tracing.py` L58
- `OTEL_SDK_DISABLED` — `hal/tracing.py` L41
- `HAL_LOG_LEVEL` — `hal/logging_utils.py` L77
- `HAL_LOG_JSON` — `hal/logging_utils.py` L92
- `FALCO_LOG_PATH` — `hal/security.py` L31
- `ORION_AUDIT_LOG` — `hal/trust_metrics.py` L193

These values don't appear in the `Config` dataclass, can't be validated at startup,
and won't show up in any config-dump debugging tool. Five of the eight
(`PROM_PUSHGATEWAY`, `HAL_INSTANCE`, `HAL_LOG_JSON`, `HAL_LOG_LEVEL`,
`OTLP_ENDPOINT`) are documented in the OPERATIONS.md `.env` table. The remaining
three (`OTEL_SDK_DISABLED`, `FALCO_LOG_PATH`, `ORION_AUDIT_LOG`) are undocumented
outside their module docstrings.

### F-73 · LOW · `open` · Verified 2026-03-15

**17 env vars not in OPERATIONS.md `.env` reference table**
The OPERATIONS.md table (L71–107) lists 23 env vars. The actual set is larger:

From `hal/config.py` (L93–141), 14 env vars are loaded but not in the table:
`INFRA_BASE` (L110), `STATIC_DOCS_ROOT` (L111), `HARVEST_SYSTEMD_UNITS` (L114),
`LAB_HOSTNAME` (L117), `LAB_HARDWARE_SUMMARY` (L118), `JUDGE_EXTRA_SENSITIVE_PATHS`
(L120), `LLM_TEMPERATURE` (L122), `LLM_TOP_P` (L123), `LLM_MIN_P` (L124),
`LLM_REPETITION_PENALTY` (L125), `WATCHDOG_DISK_RATE_PCT_PER_HOUR` (L129),
`WATCHDOG_MEM_RATE_PCT_PER_HOUR` (L132), `WATCHDOG_SWAP_RATE_PCT_PER_HOUR` (L135),
`WATCHDOG_GPU_VRAM_RATE_PCT_PER_HOUR` (L138).

From shadow config (see F-72), 3 more are undocumented: `OTEL_SDK_DISABLED`,
`FALCO_LOG_PATH`, `ORION_AUDIT_LOG`.

Operators cannot discover or tune these without reading source code.

### F-76 · LOW · `open` · Verified 2026-03-15

**Tempo deploy script binds ports to all interfaces**
`ops/deploy-tempo.sh` L56–57: The suggested docker-compose snippet binds
`"4318:4318"` (OTLP HTTP) and `"3200:3200"` (query API) without specifying
`127.0.0.1:`. Additionally, `ops/tempo.yaml` L16 configures the OTLP receiver
itself as `endpoint: "0.0.0.0:4318"`. Both the port mapping and the internal
listener bind to all interfaces. Tempo has no authentication — any LAN device
can inject traces or query the trace store.

### F-77 · LOW · `open` · Verified 2026-03-15

**`pip-audit` not part of `make check`**
`Makefile` L36: `check: lint lint-md format-check typecheck test doc-drift`.
Dependency vulnerability scanning (`pip-audit`, at `Makefile` L31) is a separate
`make audit` target, not included in `check`. Known-vulnerable packages could be
committed without CI catching them. Deliberate tradeoff (pip-audit requires network
and is slow) but worth documenting explicitly.

### F-79 · LOW · `open` · Verified 2026-03-15

**vllm.service contains hardcoded user path**
`ops/vllm.service` L10: `ExecStart=/home/jp/vllm-env/bin/vllm serve ...`. The absolute
path is specific to user `jp` and venv location. OPERATIONS.md L397 documents this as
a known trap. If the username or venv location changes, the unit silently fails.

### F-80 · LOW · `open` · Verified 2026-03-15

**Disabled systemd units have no `Conflicts=` guard**
`ops/server.service` L16–17 and `ops/telegram.service` L16–17 have full `[Install]`
sections with `WantedBy=default.target`. OPERATIONS.md L136 describes them as
"disabled — kept as rollback path only." No `Conflicts=` directive prevents them from
running simultaneously with the Docker Compose deployment. Accidentally enabling both
paths would cause port 8087 conflicts (server.service) or duplicate Telegram polling
(telegram.service).

### F-81 · LOW · `open` · Verified 2026-03-15

**gpu-metrics timer has no execution timeout**
`ops/gpu-metrics.service` L4–6: `Type=oneshot` with no `TimeoutStartSec=`.
`ops/gpu-metrics.sh` L11: `set -euo pipefail` but no `timeout` wrapper around
`nvidia-smi` (L18–20). `ops/gpu-metrics.timer` L6: `OnUnitActiveSec=15s`.
If the GPU driver hangs (common during CUDA OOM), `nvidia-smi` blocks indefinitely,
preventing subsequent 15-second timer invocations from firing.

### F-82 · LOW · `open` · Verified 2026-03-15

**No systemd hardening directives on user units**
`ops/server.service`, `ops/telegram.service`, `ops/vllm.service`,
`ops/watchdog.service`, `ops/harvest.service`, `ops/gpu-metrics.service`: None use
systemd hardening directives (`ProtectSystem=`, `NoNewPrivileges=`, `PrivateTmp=`,
`MemoryMax=`, etc.). These are user units (not system), so the blast radius is
limited to the user's session (uid `jp`), but hardening is still defense-in-depth.

### F-84 · LOW · `open` · Verified 2026-03-15

**deploy-tempo.sh relies on interactive user input**
`ops/deploy-tempo.sh` L76: `read -rp "Have you added the Tempo service to
docker-compose.yml? [y/N] "` blocks on user input. This makes the script unusable
in CI or non-interactive contexts. The script also does not validate the resulting
YAML after the user manually pastes the snippet.

### F-96 · LOW · `open` · Verified 2026-03-15

**Host `/etc` bind-mounted read-only into container**
`docker-compose.yml` L38–39: `- /etc:/mnt/host-etc:ro`. The entire host `/etc`
directory is mounted into the container. While read-only and accessed by non-root
user `hal`, this exposes host configuration: `/etc/passwd` (usernames),
`/etc/fstab` (mount layout), `/etc/hostname`, systemd unit files, and any
world-readable config files. Sensitive files like `/etc/shadow` are not
world-readable (0640) so they remain protected.

Used by: `harvest/collect.py` reads host configs for the KB. Narrower mounts
(e.g., `/etc/os-release`, specific service configs) would follow least-privilege.

### F-97 · LOW · `open` · Verified 2026-03-15

**Main container lacks Docker security hardening**
`docker-compose.yml` L13–14: Only `security_opt` is `label:disable` (SELinux).
No `cap_drop: [ALL]`, no `security_opt: [no-new-privileges:true]`, no `pids_limit`,
no `read_only: true`. The container retains the full default Docker capability set.
The process runs as non-root `hal` (Dockerfile L38: `USER hal`), which limits
exploitability, but defense-in-depth would drop unnecessary capabilities.

The sandbox container (`hal/sandbox.py`) enforces `--network none`, `--read-only`,
`--pids-limit`, `--memory`, and `--cpus` at runtime — but the main HAL container
does not apply equivalent hardening.

### F-98 · LOW · `open` · Verified 2026-03-15

**Stale Dockerfile comment — "overridden by read-only mount in compose"**
`Dockerfile` L24: `# Copy application code (overridden by read-only mount in compose)`.
`docker-compose.yml` has no source-code bind mount — source code is baked into the
image. OPERATIONS.md L235 confirms: "Source code lives inside the image — there is
no source code bind mount." The comment is a leftover from the pre-image-based
deployment era (before PR #33/#34).

### F-99 · LOW · `open` · Verified 2026-03-15

**Rollback unit defaults to localhost — not documented**
`ops/server.service` L9: `ExecStart=%h/orion/.venv/bin/python -m hal.server` — no
`--host` flag. `hal/server.py` L571: `argparse` default is `--host 127.0.0.1`.
`ops/supervisord.conf` L10: `command=python -m hal.server --host 0.0.0.0` — the
Docker path explicitly binds to all interfaces.

OPERATIONS.md L269–273 ("Rollback to bare-metal") instructs operators to
`systemctl --user enable --now server.service` but does not mention that the server
will only listen on `127.0.0.1` — not on the LAN. An operator expecting LAN access
after rollback would find HAL unreachable from other devices.

---

## 1E — Observability & Trust

### F-102 · HIGH · `open` · Verified 2026-03-15

**Watchdog metric alerts mark cooldown even when ntfy fails — silent alert loss**
`hal/watchdog.py` L462–474: After `_send_ntfy()` is called, the return value `ok` is
checked only for logging (L465–470: logs "ntfy FAILED"). The state update at L472–474
(`state[key] = now` for each fired key) runs unconditionally, regardless of whether
the notification was delivered. Result: if ntfy is unreachable, the alert is marked
as "sent" with a 30-minute cooldown. For the next 30 minutes the alert is suppressed
even though the operator never received it. The alert is silently lost.

### F-103 · HIGH · `open` · Verified 2026-03-15

**Watchdog simple/boolean alerts have the same silent-loss bug as F-102**
`hal/watchdog.py` L506–516: Same pattern — `_send_ntfy_simple()` return value `ok` is
logged but the `state[key] = now` loop at L514–516 runs unconditionally. Affects NTP,
harvest lag, containers, component health, Falco, and trend alerts. Combined with
F-102, every alert type in the watchdog can be silently lost when ntfy is down.

### F-86 · MED · `open` · Verified 2026-03-15

**`check_pushgateway` hardcodes port 9092**
`hal/healthcheck.py` L215–238 (`check_pushgateway`): Derives the Pushgateway URL by
parsing `config.prometheus_url` host and hardcoding port 9092 at L226
(`f"http://{host}:9092"`). The `PROM_PUSHGATEWAY` env var (read by
`hal/prometheus.py` L262 in `flush_metrics()`) provides a completely separate URL
mechanism. If `PROM_PUSHGATEWAY` points to a non-standard host or port, the health
check still probes 9092 on the Prometheus host.

### F-87 · MED · `open` · Verified 2026-03-15

**`check_grafana` hardcodes port 3001**
`hal/healthcheck.py` L241–262 (`check_grafana`): Same pattern as F-86 — derives host
from `config.prometheus_url` and hardcodes port 3001 at L250
(`f"http://{host}:3001"`). If Grafana runs on a different host or port, the health
check silently reports "down" with a misleading connection-refused error.

### F-104 · MED · `open` · Verified 2026-03-15

**`flush_metrics()` silently suppresses all Pushgateway POST errors**
`hal/prometheus.py` L285: `contextlib.suppress(requests.exceptions.RequestException)`
swallows every HTTP error from the Pushgateway POST — no logging, no return value, no
counter. If Pushgateway goes down, all HAL metrics silently stop being recorded. The
operator has no way to know from HAL's logs that metric push is failing. The heartbeat
thread (L293–310) calls `flush_metrics()` every 30 seconds, compounding this: 30s of
silent failure per cycle, indefinitely.

### F-105 · MED · `open` · Verified 2026-03-15

**`setup_tracing()` catches broad `Exception` at INFO log level**
`hal/tracing.py` L77: After the targeted `ImportError` catch at L75, a second
`except Exception as exc` block catches any SDK misconfiguration error (invalid
resource attributes, bad exporter config, etc.) and logs at INFO level: `"Tracing
setup failed (%s) — continuing without tracing"`. This is indistinguishable from the
"not installed" INFO message at L76. An operator reviewing logs sees the same log
level for "OTel is correctly not installed" and "OTel is installed but broken."

### F-106 · MED · `open` · Verified 2026-03-15

**`get_action_stats()` compiles LLM-supplied regex — potential ReDoS**
`hal/trust_metrics.py` L328: `re.compile(pattern, re.IGNORECASE)` where `pattern`
comes from the LLM tool call arguments (via `_handle_get_action_stats` in
`hal/tools.py` L222). The `re.error` catch at L329 handles compilation failures, but
not execution-time backtracking. A pathological regex like `(a+)+b` would cause
exponential backtracking when `regex.search()` runs at L338 and L372 against each
audit log line. Python's `re` module has no built-in backtracking timeout. Risk
depends on audit log size (see F-27).

### F-107 · MED · `open` · Verified 2026-03-15

**Falco noise filter runs before priority check — high-priority events can be suppressed**
`hal/watchdog.py` L263–267 (`_check_falco` loop body): `is_falco_noise(event)` is
checked at L263 *before* the priority check at L265. If Falco escalates a normally
informational rule to Critical/Emergency priority (via override or threshold), the
event is still filtered as noise because the noise filter (`hal/falco_noise.py` L20–27)
checks only `proc.name` and `fd.name`, ignoring `priority` entirely. The noise rules
are narrow (4 specific proc.name values, exact match at L26: `proc == p`), so real
attack risk is low — but the ordering is semantically wrong.

### F-24 · LOW · `open` · Verified 2026-03-15

**WatchdogJudge docstring contradicts implementation**
`hal/watchdog.py` L295–306: Docstring at L296 says "approves tier 0 and 1, denies the
rest." Actual behavior: `_request_approval()` at L303 returns `False` unconditionally.
The parent `Judge.approve()` (judge.py L861) auto-approves tier 0 without calling
`_request_approval`, but tier 1 calls `_request_approval` and gets denied — **unless**
trust evolution (L854–858) has already reduced it to tier 0. The docstring is
misleading: tier 1 is conditionally approved only via trust evolution, not
unconditionally.

### F-27 · LOW · `open` · Verified 2026-03-15

**Audit log read in full on every Judge init**
`hal/judge.py` L748 (`Judge.__init__`): Constructor calls `_load_trust_overrides()`
(standalone function at L664) which reads the entire `~/.orion/audit.log` file line by
line. In server mode, a fresh `ServerJudge` is created once at startup (acceptable).
In REPL mode, a single `Judge()` is also created once. The
`_refresh_trust_overrides()` method (L822) only re-reads when the file size changes,
which is efficient. This finding is LOW because the init-time read happens once, but
the audit log is unbounded — a very large log would slow startup.

### F-88 · LOW · `open` · Verified 2026-03-15

**pgvector health check may expose connection details in error responses**
`hal/healthcheck.py` L121–144 (`check_pgvector`): The `except Exception as exc`
handler at L143 puts `str(exc)` into `ComponentHealth.detail`. For psycopg2 connection
errors, the exception string typically includes host, port, dbname, and user (password
is masked by psycopg2 as `***`). This detail is returned by the `/health/detail`
endpoint (`hal/server.py` L368–401) which requires auth. The same pattern exists for
all 8 check functions — `str(exc)` at L84, L118, L144, L163, L212, L238, L262, L286
— any of those exceptions could leak infrastructure details (hostnames, ports, paths).

### F-108 · LOW · `open` · Verified 2026-03-15

**`_save_state()` uses non-atomic file write — crash loses all cooldowns**
`hal/watchdog.py` L70–72: `_save_state()` calls `STATE_FILE.write_text(json.dumps(...))`
which internally does `open(path, "w")` (truncates file) then writes content. If the
process is killed between the truncate and the write completing, the state file is
empty or partial. On next run, `_load_state()` (L63–66) catches `JSONDecodeError` and
returns `{}`, losing all cooldown timestamps. All alerts would re-fire immediately.
Low severity because this requires a crash at the exact wrong millisecond.

### F-109 · LOW · `open` · Verified 2026-03-15

**`PrometheusClient` methods silently return empty/None on all errors — no logging**
`hal/prometheus.py` L22–34 (`query()`), L36–43 (`scalar()`), L84–118
(`range_query()`): All three methods catch `requests.exceptions.RequestException` and
return `[]` or `None` with no logging. The `trend()` method at L122 inherits this via
`range_query()`. Callers (watchdog, agent, health check) cannot distinguish
"Prometheus is down" from "this metric has no data." The watchdog works around this
with a separate `prom.health()` exception catch at `run()` L427–433, but the agent's
metrics-seed path does not.

### F-110 · LOW · `open` · Verified 2026-03-15

**`get_action_stats()` reads audit log file twice per call**
`hal/trust_metrics.py` L320–322 (`events = list(load_audit_log(path))`) reads the
entire file for approval events. Then L365 (`for oev in load_outcome_log(path)`) reads
the same file again for outcome events. Both functions open, iterate, and parse the
file independently. For a large audit log this doubles I/O. Related to F-27 (unbounded
log size).

### F-111 · LOW · `open` · Verified 2026-03-15

**Recovery notification failures in `_attempt_recovery()` silently ignored**
`hal/watchdog.py` L342 and L355: `_send_ntfy_simple()` is called to notify the
operator of recovery success/failure, but the return value is discarded in both
branches. If ntfy is down during a recovery attempt, the operator never learns about
it. The `_log()` calls at L341 and L354 write to the local watchdog log file, but
there is no push notification fallback.

### Unknowns (cannot verify from code alone)

1. **UNKNOWN-1:** Does Falco log rotation happen externally (e.g., logrotate)? If
   not, `_check_falco`'s `tail -n 200` degrades as the log grows unboundedly.

2. **UNKNOWN-2:** Is Pushgateway reachable from inside the Docker container?
   `PROM_PUSHGATEWAY` typically uses `localhost:9092`, which would fail inside a
   container unless `network_mode: host` or a Docker-internal address is used.

3. **UNKNOWN-3:** Does the watchdog systemd timer have `TimeoutStopSec` or
   `KillMode` set? If a watchdog run hangs due to stacked health check timeouts
   (8 checks × 5s = 40s worst case), systemd may stack another run on top.

4. **UNKNOWN-4:** Does psycopg2 include the password in `OperationalError` strings
   for the version installed? Psycopg2 ≥ 2.8 masks it with `***`, but older versions
   may not. Needs runtime check to confirm F-88 severity should stay LOW or escalate.

5. **UNKNOWN-5:** Are `opentelemetry-*` packages in the production Docker image?
   `requirements.txt` would need to list them, otherwise tracing is always no-op in
   production and F-105 is moot.

---

## 1F — Docs & Prompt Drift

### F-58 · MED · `open`

**OPERATIONS.md ground-truth boost value disagrees with code**
`OPERATIONS.md` L208: "Ground-truth docs get a +0.10 score boost in KB search results."
`hal/knowledge.py` L18: `_GROUND_TRUTH_BOOST = 0.15`.
The documentation understates the boost by 50%. Anyone tuning retrieval quality based
on the docs would use the wrong number.

### F-89 · MED · `open`

**System prompt hardcodes KB chunk count**
`hal/bootstrap.py` L60 (`get_system_prompt`): The system prompt string contains
`"~19,900 doc chunks"`. This is a hardcoded literal — not dynamically computed from
the actual database count. As the KB grows or shrinks (harvest additions, reference
doc changes), the number in the prompt drifts from reality. The LLM may cite this
wrong number when asked about the KB.

---

## Dropped findings

These were reported by delegated audit chats but invalidated by direct code reads:

| ID | Reason dropped |
| --- | --- |
| F-21 | `hal/web.py` L227–235: `fetch_url()` uses `stream=True` + 1 MB cap. Response size IS limited. |
| F-32 | `hal/knowledge.py` L40–42: `KnowledgeBase.__init__` stores DSN and LLM ref only. Connection is lazy (on first `search()`/`remember()`). No eager connection. |
| F-39 | "Double classify in server path" — incorrect. `server.py` L530 does NOT pass `classifier=` to `dispatch_intent()`. There is only one `classify()` call at L508, for response metadata only. The real issue (conversational routing disabled) is now captured as F-90. |
| F-49 | "DSN masking assumes `@` in string" — no DSN masking code exists anywhere in the codebase. Confabulated by delegated chat. |
| F-70 | `docker-compose.yml` L19–22: Resource limits DO exist: `memory: 2G`, `cpus: "4"`. |
| F-78 | `requirements.lock` and `requirements-dev.lock` ARE git-tracked (confirmed via `git ls-files`). |

## Resolved findings

| ID | Resolution |
| --- | --- |
| F-71 | Watchdog interval was listed as "30min" in SUMMARY.md but actual is 5min (`ops/watchdog.timer` `OnUnitActiveSec=5min`). Corrected in SUMMARY.md on 2026-03-15. |
