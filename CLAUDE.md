# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## ⛔ REQUIRED FORMAT — Before Every Code Change

**This applies to every single change, no exceptions. Violations are drift.**

For each proposed change I must output exactly this block and then **STOP and wait**:

```markdown
### Item N — <short title>

**Root cause (not symptom):** <what is actually wrong and why>

**What I propose:** <exact files and lines I will touch, and what I will do>

**Why this is correct long-term:** <not just "it fixes the symptom">

**Confidence:** I KNOW this is right / I am GUESSING because <reason>
```

I do **not** write or change any code until the operator replies with approval.
After the operator approves, I make **exactly one change**, verify it, commit it,
then present the **next** item in the same format and stop again.

**"One change" is not open to interpretation:** one finding number = one commit. Each
item gets its own proposal block, its own approval, its own `pytest` run, its own commit.

The only exception: a change that is **mechanical and zero-risk** (e.g. a 2-line
whitespace or import fix) may be grouped with the preceding item **only if I explicitly
state** "I am grouping this with the above as a single commit because it is trivially
mechanical" **and the operator confirms it**. Grouping without that explicit exchange is
a violation.

If I skip this format, the operator should say **"format"** and I will stop, restate
the plan correctly, and wait.

If I batch items without permission, the operator should say **"split"** and I will
re-propose them separately.

---

## ⛔ CLAUDE.md Maintenance Rule

**This file is a reference document, not a changelog or session journal.**

- **Update in place.** When facts change (new service, new file, new tool), edit the
  relevant existing section. Never append a new "Done" or "Session N" block.
- **Do not add session logs.** Git history is the changelog. This file describes
  *current state*, not *how we got here*.
- **If a section is growing beyond its original scope**, that is drift. Condense it.
- **Implementation details** (test counts, intermediate thresholds, migration steps, item
  numbers) belong in commit messages, not here.

If I catch myself adding a changelog section, I must stop and instead update the
existing "Current State" section in place.

---

## How I (Claude) Work With the Operator

Observability aid: I will also emit structured logs with session_id and trace correlation for each approved change when running code paths, and I will update README and SESSION_FINDINGS as I go to prevent documentation drift. These logs are JSON by default and can be toggled with HAL_LOG_JSON.

**The reason this section exists:** I drift on long projects. Each individual fix can seem
logical in isolation, but over many sessions and context resets I lose the thread of what
we're actually building and start optimising for "make the immediate problem go away" instead
of "build something genuinely reliable." The operator cannot see this drift from the outside —
each thing I do looks plausible, the code runs, the symptom disappears. The only way to
surface drift is to force me to explain my reasoning in full before every action, because when
I'm drifting the explanation will sound wrong or thin. That is the catch mechanism.

**Rules — no exceptions:**

1. **Explain before acting.** Before writing or changing any code I must state:
   - What I think the problem actually is (root cause, not symptom)
   - What I propose to do and why this approach is correct long-term
   - Whether I *know* this is right or whether I am *guessing*
   Then wait for the operator to agree before proceeding.

2. **One change at a time.** Make one change, verify it works, then move to the next.
   Multiple simultaneous changes make it impossible to know what worked or broke.

3. **No bandaids.** If I find myself adding rules, caps, flags, or prompt instructions to
   work around a misbehaving component, I must stop and ask: is the component itself wrong?
   Patching symptoms is how drift accumulates silently.

4. **Say "I'm guessing" out loud.** If I don't fully understand why something is broken,
   I say so explicitly before proposing a fix. Confident-sounding guesses are the most
   dangerous thing I do.

---

## Documentation

Read these before working on the relevant area. They are the source of truth — not this file.

| Doc | What it covers |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Component map, data flow, design rationale (intent routing, Judge, agent loop, LLM backend split, memory, observability, KB pipeline, security stack) |
| [OPERATIONS.md](OPERATIONS.md) | Lab host details, services table, `.env` reference, systemd units, deploy procedures, known traps, secrets |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev workflow, test commands, linting, eval harness, git conventions, branch policy |
| [ROADMAP.md](ROADMAP.md) | What's been done (chronological), backlog, architectural backlog, end-state vision |
| [knowledge/LAB_ENVIRONMENT.md](knowledge/LAB_ENVIRONMENT.md) | Ground-truth lab description — hardware, services, network, dev machine |
| [README.md](README.md) | Project overview, quick start, slash commands, key files table |

---

## Current State

HAL is fully operational on the-lab (192.168.5.10). All core components working:

- **LLM**: vLLM serving Qwen2.5-32B-Instruct-AWQ (port 8000); Ollama embeddings-only on CPU
- **LLM tool-call fallback parsing**: `<tool_call>/<tools>` content extraction is opt-in via `HAL_EXTRACT_FALLBACK=1`; default is disabled to prevent phantom tool-call injection from free-text examples
- **Intent routing**: embedding classifier routes to conversational, health, fact, or agentic handlers
- **Agent loop**: tool dispatch via registry (`hal/tools.py`); Planner/Critic sub-agents gated by query complexity; `get_trend` tool for PromQL range-query trend analysis (rising/falling/stable, 1h–24h window)
- **Judge**: tier 0-3 policy gate with evasion detection, git write blocking, path canonicalization, self-edit governance, default-deny; JSON audit log
- **Knowledge base**: ~19,900 chunks in pgvector; three-layer model (ground-truth, reference, live-state, memory); nightly harvest at 3am
- **Security**: Falco, Osquery, ntopng, Nmap workers — all Judge-gated
- **Web tools**: `web_search` (Tavily, conditional on API key), `fetch_url` (SSRF-protected)
- **Interfaces**: terminal REPL, FastAPI HTTP server (`/chat`, `/health`), Telegram bot
- **Monitoring**: watchdog (CPU, mem, disk x3, swap, load, GPU VRAM/temp, NTP, containers, Falco); ntfy alerts + recovery notifications
- **Observability**: OTel tracing, Pushgateway metrics, Grafana dashboard
- **Memory**: SQLite sessions with poison-turn filter and 30-day pruning; `/remember` facts in pgvector
- **Configuration safety**: `OLLAMA_HOST`, `PGVECTOR_DSN`, and `PROMETHEUS_URL` are required at startup; missing values raise a clear `.env.example` RuntimeError
- **Test suite**: 544 offline tests passing (`pytest tests/ --ignore=tests/test_intent.py`); intent tests require reachable Ollama

**Known issues:** See [ROADMAP.md](ROADMAP.md) backlog section.
