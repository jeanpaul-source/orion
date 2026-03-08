# Chat 12 — Production Code Audit

> **Prompt style:** Guardrails not rails (see `notes/prompt-style-guide.md`)
> **Branch:** none — this is a read-only audit. No code changes.

---

## Mission

**What:** Read every Python module in `hal/` and produce a ranked findings list.
Flag shortcuts, band-aids, outdated workarounds, dead code, structural smells,
and genuine bugs. Do not fix anything — just find and classify.

**Why now:** Chats 2–11 were a rapid build-out: hardening, features, tests,
infra. Each chat was individually sound, but fast iteration leaves residue —
patterns that made sense mid-build but are now inconsistent with the mature
architecture, workarounds for problems that were later fixed properly, and
copy-paste that should have been consolidated.

**Why code first, not tests:** The tests are the safety net. Audit what the
net protects first. If production code changes based on this audit, the
existing 1,176 tests catch regressions. If we audited tests first, then fixed
production code, we'd break the tests we just fixed.

---

## Scope

**In scope:** All 31 Python files in `hal/` (8,544 lines) + 6 files in
`harvest/` (~1,065 lines). Total: ~9,600 lines.

**Out of scope (for now):**

- `tests/` — that's Pass 2, after production code is cleaned up
- `eval/` — evaluation harness, rarely changes
- `scripts/` — one-off tooling
- `ops/` — operational configs (different audit type)
- Documentation files — already maintained via doc-drift checks

---

## Severity definitions (with Orion-specific examples)

### P0 — Will cause a bug, data loss, or security bypass

Things that are actually broken or will break under realistic conditions.
**In this codebase, P0 means:**

- A code path that runs a shell command or Docker exec without going through
  `judge.approve()` (Judge bypass = security violation of the core architecture)
- An exception that crashes the REPL, HTTP server, or Telegram bot process
- Data corruption in `memory.db`, the audit log, or pgvector
- A security hole that lets user input escape the sandbox or SSRF protections

### P1 — Architectural smell (works today, breaks tomorrow)

Code that works but violates the project's own conventions, creates
maintenance traps, or will silently break when infrastructure changes.
**In this codebase, P1 means:**

- Hardcoded ports, IPs, or paths that duplicate values already in `config.py`
  (guaranteed to drift when the lab changes)
- Error handling that silently swallows failures — makes it impossible to
  distinguish "service is down" from "query returned no data"
- Two modules implementing the same concept differently (one env-configurable,
  the other hardcoded) — the inconsistency is the smell
- Unbounded resource consumption (reading files that grow forever, no log
  rotation, no cap on accumulated data)

### P2 — Cleanup opportunity

Correct code that could be simpler, clearer, or more idiomatic. Not urgent.

### "Intentional" — Not a finding

Document it, explain why it exists, and note whether the justification still
holds. Known intentional patterns from `SESSION_FINDINGS.md`:

- P1 (control token stripping) — model behavior workaround
- P2 (loop-breaking user message injection) — prevents infinite tool loops
- P3 (forced no-tools on final iteration) — ensures text response
- P5 (Judge `_llm_reason()` system prompt) — documented as low-risk

---

## Specific investigation targets

These are not guesses — they are confirmed leads from a pre-audit sweep of the
codebase. The audit must investigate each one, confirm or refute it with exact
line numbers, and classify the severity.

### A. Judge bypass paths

The architecture says **every** action goes through `judge.approve()`. Check
these specific locations:

1. **`sandbox.py` cleanup:** The `finally` block in `execute_code()` runs
   `executor.run(f"rm -f {path}")` directly — no Judge call, no audit log
   entry. Path is internally generated (`/tmp/hal-sandbox-{uuid}.py`) so
   injection risk is low, but it's an ungated shell command on principle.

2. **`main.py` `/run` slash command:** `cmd_run()` calls `executor.run()`
   after `judge.approve()`, but bypasses the `dispatch_tool()` pipeline.
   This means no output capping (8000 char limit), no `record_outcome()` for
   trust evolution, and no metrics instrumentation.

3. **`sandbox.py` `execute_code()` itself:** Judge gating happens in
   `dispatch_tool()` at the caller level, not inside `execute_code()`. If
   anyone calls `execute_code()` directly in a future module, the Judge is
   bypassed. The docstring says "caller must gate" — is that sufficient?

4. **Verify all other tool handlers:** Confirm every handler in the registry
   goes through `judge.approve()` via the dispatch path. Don't assume — read
   the code.

### B. Silent error swallowing

These modules catch exceptions and discard diagnostic information:

1. **`prometheus.py`:** `query()`, `scalar()`, and `range_query()` all catch
   exceptions and return empty/None with no logging whatsoever. If Prometheus
   is unreachable, HAL silently has no metrics — and the operator can't tell
   why from any log.

2. **`tracing.py`:** `setup_tracing()` has a `except Exception as exc` after
   the `ImportError` handler. The `ImportError` catch is correct (optional
   dep). The broad `Exception` catch masks real configuration bugs and logs
   them as INFO.

3. **`judge.py` `_load_trust_overrides()`:** Returns `{}` on any `Exception`.
   A corrupt audit log silently disables all trust promotions *without any
   warning*. The operator thinks trust evolution is working; it isn't.

4. **Survey all `except Exception` and `except:` across `hal/*.py`.** Build a
   complete catalog. For each: is the exception structural (expected failure
   mode) or defensive (hiding bugs)?

### C. Hardcoded values that shadow config

These create guaranteed drift when infrastructure changes:

1. **`telegram.py`:** `HAL_CHAT_URL = "http://127.0.0.1:8087/chat"` is a
   module-level constant. Port 8087 and host `127.0.0.1` are baked in. If the
   server port changes, the Telegram bot silently points at nothing.

2. **`healthcheck.py`:** `check_pushgateway()` extracts the host from
   `config.prometheus_url` then hardcodes port 9092. `check_grafana()` does
   the same with port 3001. `config.py` already has `prom_pushgateway` with
   the full URL — the healthcheck ignores it.

3. **`watchdog.py` vs `security.py`:** Both define `FALCO_LOG` as
   `/var/log/falco/events.json`. But `security.py` reads from
   `FALCO_LOG_PATH` env var with that default, while `watchdog.py` hardcodes
   it with no env override. One is configurable; the other isn't. If someone
   sets `FALCO_LOG_PATH`, the watchdog ignores it.

4. **`bootstrap.py` system prompt:** Contains literal hardware specs
   (RTX 3090 Ti, 64 GB RAM), interface names (`enp130s0`), mount paths, and
   version numbers. This is flagged in ROADMAP.md Path C item 1 — verify it's
   still there and note the scope.

5. **`agent.py` / `memory.py`:** KB seeding threshold `0.75` is inline at the
   call site, not in config. `TURN_WINDOW = 40` is a constant in `memory.py`
   that affects context window behavior — not operator-configurable.

### D. Sandbox Docker security

`sandbox.py` builds a `docker run` command for untrusted code execution.
Check the defense-in-depth flags:

1. **Missing flags:** Does the command include `--cap-drop ALL` and
   `--no-new-privileges`? These are zero-cost defense-in-depth. If a future
   Dockerfile change removes the `USER sandbox` directive, the container runs
   as root without them.

2. **`--user` flag:** The runtime command should explicitly pass
   `--user sandbox:sandbox` rather than relying solely on the Dockerfile's
   `USER` directive. Defense in depth.

3. **Host temp file exposure:** User code is written to `/tmp/hal-sandbox-{uuid}.py`
   on the host, then bind-mounted. It's cleaned up in `finally`. The UUID
   makes it unpredictable, but the code is briefly readable by other host
   processes. Note this as a P2.

### E. SSRF / DNS rebinding in `web.py`

The SSRF protection has a known architectural limitation:

1. **TOCTOU window:** `_validate_url()` resolves DNS and checks IPs. Then
   `requests.get()` re-resolves DNS internally. Between resolution 1 and
   resolution 2, a DNS rebinding attack could swap the A record from public
   to `127.0.0.1`. The redirect re-validation catches *post-redirect*
   rebinding but not the initial fetch. This is mitigated by the tool being
   tier 1 (requires approval) — but document the gap.

2. **`sanitize_query()` IPv6 gap:** The function strips RFC1918 and loopback
   IPv4 addresses from Tavily search queries, but not IPv6 private ranges
   (`fe80::`, `fd00::`, `::1`) or Tailscale CGNAT (`100.64-127.x.x`). Low
   practical risk but an incomplete filter.

### F. Double work in the HTTP path

1. **Double intent classification in `server.py`:** The `/chat` endpoint
   calls `classifier.classify(query)` to get the intent label for the response
   payload, then calls `dispatch_intent()` which classifies *again*. Every
   HTTP request embeds the query twice via Ollama (~50ms wasted, doubled
   embedding load).

### G. Big module structure

These modules are large. The question isn't "split them?" — it's "are the
pieces inside them cohesive or accidental?"

1. **`judge.py` (996 lines):** Contains rule tables (~120 lines of pure
   data), classification logic (~200 lines), trust evolution (~80 lines), and
   the Judge class itself (~150 lines). Are these four concerns separable
   without breaking the module's API? Would splitting improve or hurt
   discoverability?

2. **`tools.py` (962 lines):** ~490 lines are JSON schema definitions, ~470
   are handler functions. Schemas are co-located with handlers for
   discoverability. Is this a reasonable trade-off, or is the file
   unwieldy for code review?

3. **`_load_trust_overrides()` in `judge.py`:** Reads the *entire* audit log
   file on every Judge initialization. The audit log has no rotation. After
   months of operation, how large will this file be? What happens to startup
   time?

### H. Harvest pipeline robustness

`harvest/` runs unattended at 3am via systemd timer. Failures must be visible,
not silent. The same OllamaClient and pgvector patterns from `hal/` apply here.

1. **Transaction safety in `ingest.py`:** `clear_lab_docs()`,
   `clear_ground_truth()`, and `clear_static_docs()` each call `conn.commit()`
   independently. New rows are only inserted later, with a final `conn.commit()`
   at the end of `ingest()`. If the process crashes between the clears and the
   final commit, the DB is left with zero rows for those categories — all old
   data deleted, no new data written. Is there a single-transaction boundary?

2. **Silent subprocess failures in `collect.py`:** `_run()` calls
   `subprocess.run(shell=True)` and returns `stdout.strip()`. Non-zero exit
   codes and stderr are both silently discarded. A failing `docker ps` or
   `df -h` produces an empty doc with no warning. The `# noqa: S602` comment
   says "all callers pass hardcoded command strings" — but at least one caller
   (`collect_system_state`) interpolates `ollama_host` from config into the
   shell command. Is the noqa accurate?

3. **Triple-defined `STATIC_DOCS_ROOT`:** The path `/data/orion/orion-data/
   documents/raw` appears in `ingest.py` as `STATIC_DOCS_ROOT`, in
   `collect.py` as `_STATIC_DOCS_ROOT`, and in `hal/config.py` as
   `config.static_docs_root`. If the env var changes, `collect.py` follows it
   but `ingest.py`'s `clear_static_docs()` still deletes rows matching the old
   hardcoded prefix.

4. **`print()` instead of structured logging:** `collect.py` and `main.py`
   use bare `print()` for output, while `parsers.py` correctly uses
   `logging.getLogger()`. Harvest output can't be filtered by log level
   or formatted as JSON. This violates the project's own python instructions.

5. **Snapshot silent empties:** `snapshot.py` parsers return `[]` when content
   doesn't match expected formats. There's no distinction between "data
   unavailable" and "legitimately empty" — a silent `docker ps` failure
   (Finding H.2) produces the same snapshot as a host with no containers.

---

## Known existing debt (verify, don't re-discover)

These are already tracked. The audit should confirm their current status —
still present, resolved, or worse than documented:

### SESSION_FINDINGS.md band-aids

| ID | Description | Last known status |
|---|---|---|
| P1 | Control token stripping (`_CONTROL_TOKEN_RE`) | Present — intentional |
| P2 | Loop-breaking user message injection | Present — intentional |
| P3 | Forced no-tools on final iteration | Present — intentional |
| P4 | Tool result missing `tool_call_id` | ✅ Resolved |
| P5 | Judge `_llm_reason()` system prompt | Pending, low-risk |

### ROADMAP.md architectural backlog (Path C)

| Item | Description | Status |
|---|---|---|
| C1 | Template system prompt from Config | Open |
| C2 | Externalize Judge patterns | Open |
| C3 | Remove hardcoded defaults from config | ✅ Done |
| C4 | Pluggable harvest collectors | ✅ Done |

### SESSION_FINDINGS.md root causes

| ID | Description | Likely status |
|---|---|---|
| RC1 | Model emits raw tool call JSON as text | Mitigated by `sanitize.py` + vLLM |
| RC2 | Model identity overridden by training | Mitigated by prompt hardening |
| RC3 | Session history propagates failures | Fixed — poison filter + pruning |
| RC4 | No conversational category | ✅ Fixed |
| RC5 | KB seeding unconditional | ✅ Fixed — threshold 0.75 |
| RC6 | harvest_last_run missing | ✅ Fixed |

---

## How to conduct the audit

### Read order

Leaves first, orchestration last. Understand building blocks before auditing
the modules that compose them.

**Tier 1 — Leaf modules (no hal.* imports):**
`falco_noise.py` (25), `notify.py` (51), `tunnel.py` (62),
`logging_utils.py` (116), `config.py` (141), `sanitize.py` (168),
`tracing.py` (138)

**Tier 2 — Domain modules:**
`executor.py` (117), `llm.py` (179), `knowledge.py` (169),
`memory.py` (186), `prometheus.py` (309), `intent.py` (231),
`workers.py` (127), `sandbox.py` (219)

**Tier 3 — Integration modules (most findings expected here):**
`judge.py` (996), `tools.py` (962), `security.py` (260),
`web.py` (257), `trust_metrics.py` (401), `healthcheck.py` (352),
`playbooks.py` (379), `postmortem.py` (203)

**Tier 4 — Orchestration:**
`agent.py` (363), `bootstrap.py` (377), `watchdog.py` (522),
`server.py` (582), `telegram.py` (190), `main.py` (458)

**Tier 5 — Harvest pipeline (read after hal/):**
`harvest/parsers.py` (103), `harvest/collect.py` (438),
`harvest/ingest.py` (279), `harvest/snapshot.py` (162),
`harvest/main.py` (83)

**Where to spend the most time:** Tier 3 modules (`judge.py`, `tools.py`,
`healthcheck.py`, `playbooks.py`) and Tier 4 orchestration (`server.py`,
`watchdog.py`, `main.py`). These are the most complex, have the most
cross-cutting concerns, and were built across the most sessions.

Tier 1 leafs are small and stable — quick read, low finding density.

### What NOT to flag

- **Style issues** that ruff would catch — linting is enforced
- **Type annotation gaps** — mypy strict is enforced
- **Missing tests** — that's Pass 2
- **Documentation drift** — doc-drift check handles this
- **Known intentional patterns** (SESSION_FINDINGS P1–P3) — unless worse

### What TO look for beyond the specific leads above

The leads in section "Specific investigation targets" are confirmed starting
points, not the complete list. While reading each module, also check:

- **Dead code:** Functions that nothing calls, imports that nothing uses
  (beyond what ruff catches — ruff sees F401 unused imports but not unused
  *functions*)
- **Stale comments:** Comments that describe behavior from before the refactor
  in Chat 8 (Feb 26, when `bootstrap.py` was extracted from `main.py`)
- **Inconsistent error return conventions:** Some functions return `None` on
  error, some return `""`, some raise, some return a tuple — is there a
  pattern or is it arbitrary?
- **Thread safety:** `prometheus.py` has in-memory accumulators (`_counters`,
  `_gauges`) and a background heartbeat thread. Are the accumulators
  protected? Is `flush_metrics()` thread-safe?
- **Resource leaks:** File handles, HTTP connections, SSH connections that
  might not close on error paths

---

## Output format

Write a single file to `notes/audit-findings.md` structured like this:

```markdown
## Summary

- P0 findings: N
- P1 findings: N
- P2 findings: N
- Verified intentional: N
- Known debt confirmed still present: N
- Known debt confirmed resolved: N

## P0 Findings

### P0-1: <short title>
**File:** hal/example.py, lines X–Y
**What:** <specific description — cite variable/function names>
**Why it matters:** <what breaks, when, how badly>
**Suggested approach:** <one-line direction, not implementation>

## P1 Findings

### P1-1: <short title>
**File:** hal/example.py, lines X–Y
**What:** ...
**Why it matters:** ...
**Suggested approach:** ...

## P2 Findings

### P2-1: <short title>
...

## Verified Intentional Patterns

### I-1: <pattern name>
**File:** hal/example.py, lines X–Y
**Why it exists:** <justification from code/docs>
**Still justified?:** yes / no — <reasoning>

## Known Debt Status Update

### SESSION_FINDINGS P1 — Control token stripping
**Status:** still present / resolved / worse
**Notes:** ...

(repeat for each known item)
```

---

## Non-negotiables

1. **Read-only audit.** Do not create branches, edit files, or run commands
   that modify state. Output is `notes/audit-findings.md` only.
2. **Read every module.** Do not skip files. The smallest files often contain
   the most subtle problems.
3. **Ground every finding in code.** File name + line range + specific
   variable/function names. "The agent loop feels complex" is not a finding.
4. **Classify honestly.** If unsure between P0 and P1, say so and explain why.
5. **Check against existing docs.** `SESSION_FINDINGS.md`, `ARCHITECTURE.md`,
   `ROADMAP.md` all describe known issues. Cross-reference before flagging
   something as new.
6. **No implementation.** One-line approach suggestions only. Fix prompts come
   after the operator triages the findings.
7. **Follow CLAUDE.md.** Even though this is read-only, the explain-before-
   acting contract applies. If a finding seems ambiguous, state your reasoning
   for the classification.

---

## Reference docs (read before starting)

| Doc | What to check against |
|---|---|
| `ARCHITECTURE.md` | Does each module match the documented component map and data flow? |
| `SESSION_FINDINGS.md` | Band-aids (P1–P5), root causes (RC1–RC6), behavioral failures (B1–B6) |
| `ROADMAP.md` | Path C architectural backlog — verify open items are still present |
| `CLAUDE.md` | "Current State" section — does it match what the code actually does? |
| `CONTRIBUTING.md` | Conventions — does the code follow its own rules? |

---

## Current state (as of this prompt)

| Item | Value |
|---|---|
| Branch | `main` @ `e256787` (PR #11 merged) |
| Production modules | 31 files in `hal/` (8,544 lines) + 6 files in `harvest/` (~1,065 lines) |
| Test files | 36 files, 15,297 lines in `tests/` |
| Offline tests | 1,176 passing (22s) |
| Coverage | 87% (ratchet-locked) |
| mypy | 0 errors (strict) |
| ruff | clean |

---

## Completion checklist

- [ ] Every `hal/*.py` file read in full
- [ ] Every `harvest/*.py` file read in full
- [ ] All 8 specific investigation targets (A–H) addressed with findings
- [ ] Each finding has severity + file + line range + description
- [ ] Known debt items verified against current code
- [ ] No code modified
- [ ] Findings ranked P0 → P1 → P2
- [ ] Intentional patterns identified and justified
- [ ] `notes/audit-findings.md` written
