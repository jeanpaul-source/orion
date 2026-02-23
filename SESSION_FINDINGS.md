# SESSION_FINDINGS.md
_Started: 2026-02-22 | Step 1 complete — awaiting operator review before Step 2_

---

## STEP 1: CLAUDE.md Verification Report

### ✅ Confirmed Accurate

| Claim | Verified |
|---|---|
| Prometheus at port 9091 | Docker: `0.0.0.0:9091->9090/tcp` |
| Grafana at port 3001 | Docker: `0.0.0.0:3001->3000/tcp` |
| pgvector at port 5432 | Docker: `0.0.0.0:5432->5432/tcp` |
| Ollama at port 11434, bare metal systemd | `systemctl is-active ollama` → active; port 11434 listening |
| pgvector-kb-api running at port 5001 | `python3 /opt/homelab-infrastructure/pgvector-kb/api.py` running |
| Cockpit at 9090 (NOT Prometheus) | port 9090 listening, confirmed cockpit |
| Secrets tmpfs at `/run/homelab-secrets/` | `agent-zero.env`, `monitoring-stack.env`, `pgvector-kb.env` present |
| Server .env has `OLLAMA_MODEL=qwen2.5-coder:32b` | confirmed |
| Server .env has `PROMETHEUS_URL=http://localhost:9091` | confirmed |
| `vm.swappiness=10` in `/etc/sysctl.d/99-swappiness.conf` | confirmed |
| Watchdog deployed as user systemd | `watchdog.timer` active (waiting), fires every 5min (OnUnitActiveSec=5min) |
| Watchdog alerting harvest_lag to log only (ntfy not configured) | 7 log entries, all `ntfy FAILED (url=not set)` |
| `harvest_last_run` not present on server | confirmed |
| All documented `hal/*.py`, `harvest/*.py`, `tests/*.py` files exist | confirmed |
| `ops/watchdog.service`, `ops/watchdog.timer` exist | confirmed |
| `pytest.ini`, `requirements.txt`, `requirements-dev.txt`, `.env.example` exist | confirmed |
| `nomic-embed-text:latest` and `qwen2.5-coder:32b` present in Ollama | confirmed |
| Watchdog state file records `harvest_lag` cooldown | `~/.orion/watchdog_state.json` confirmed |

---

### ⚠️ Discrepancies Found

**D1 — agent-zero is completely absent (not just stopped)**
- CLAUDE.md: documents agent-zero as running at `50080:80`
- Reality: no container exists at all. `docker ps -a | grep agent` returns nothing.
- Severity: medium — CLAUDE.md service table is wrong. Unknown if intentionally decomissioned.
- Action needed: confirm whether agent-zero should be re-added to the running service table, or removed from CLAUDE.md.

**D2 — `hal/config.py` hardcoded default Prometheus port is wrong**
- CLAUDE.md: correctly documents Prometheus at port 9091
- Reality: `config.py` line 29 hardcodes `http://192.168.5.10:9090` as the default fallback
- Port 9090 is cockpit — a completely different service
- Impact: if HAL is run without a `.env` file (e.g. fresh checkout, CI, testing), Prometheus queries silently fail
- Severity: low in practice (server .env overrides to 9091), but a latent trap for anyone setting up fresh
- The `.env.example` correctly shows 9091 — the default in the Python code is inconsistent with the template

**D3 — `.env.example` has stale default model**
- CLAUDE.md: active model is `qwen2.5-coder:32b`
- `.env.example` line 6: still shows `OLLAMA_MODEL=qwen2.5-coder-14b-32k:latest`
- Severity: cosmetic — anyone copying `.env.example` to set up a new instance will get the 14b model by default, not 32b

**D4 — `hal/tunnel.py` is not documented in the CLAUDE.md file table**
- File exists, is imported and used by `hal/main.py`
- Provides SSH tunnel for the laptop-side use case (auto-tunnel when Ollama not directly reachable)
- Severity: minor omission — but it means the file table in CLAUDE.md is incomplete

**D5 — Undocumented Ollama model present**
- CLAUDE.md: lists `qwen2.5-coder:32b` and `qwen2.5-coder-14b-32k:latest` as the two installed models
- Reality: 5 models present: `nomic-embed-text:latest`, `qwen2.5-coder-32b-16k:latest`, `qwen2.5-coder:32b`, `qwen2.5-coder:14b`, `qwen2.5-coder-14b-32k:latest`
- New/undocumented: `qwen2.5-coder-32b-16k:latest` and `qwen2.5-coder:14b`
- Severity: cosmetic — doesn't affect operation, but the model inventory is stale

**D6 — `psql` CLI not installed on server**
- CLAUDE.md doesn't claim psql is installed, but any procedure that says "query pgvector" using `psql` from the shell will fail
- Reality: `psql: command not found`. The database is accessible via Python/psycopg2 only from the shell
- Severity: minor — affects diagnostics/debugging but not HAL operation

---

## STEP 2: Behavioral Map — What HAL Does vs. What It Should Do

Evidence drawn from the actual session history in `~/.orion/memory.db`.

### Failure catalog

**B1 — Model emits raw tool call JSON as plain text (most common failure)**

Observed in: sessions 40162676, 61348e14, ef83921a, 600b0cf4

What happens:
- The LLM, instead of making a proper structured tool call (which Ollama delivers via the `tool_calls` field), outputs the tool call as a JSON block in the `content` field
- The code checks `msg.get("tool_calls") or []` — finds nothing, treats the JSON as the final answer
- The user receives raw JSON

Real examples from session history:
```
user:      "What port does Prometheus run on?"
assistant: {"name": "get_metrics", "arguments": {}}

user:      "hello"
assistant: {"name": "search_kb", "arguments": {"query": "list of all the current AWS Regions..."}}

user:      "please check the lab for anything that seems off"
assistant: {"name": "<function-name>", "arguments": <args-json-object>}
```

The JSON content is always wrong in two ways:
1. It's the wrong format to show to a user (a raw tool call schema)
2. The tool chosen is usually wrong (calling `get_metrics` for a static fact question; hallucinating an AWS query for "hello")

No code path catches this. The `_CONTROL_TOKEN_RE` strips `<|...|>` tokens, but these aren't control tokens — they're the model hallucinating a response template.

---

**B2 — Model identity override**

Observed in: session 550cae47 (all 5 turns)

What happens:
- User asks "whats up man?"
- Model responds: "Hey! I'm Qwen, created by Alibaba Cloud."
- User asks "no prompt at all?" → model doubles down: "I don't have any specific 'prompt'"
- User asks "do you remember our talks?" → "I'm Qwen... I don't have the ability to recall past conversations"

This is the model's RLHF training completely overriding the SYSTEM_PROMPT. The system prompt says "You are HAL, do not refer to yourself as Qwen" — but on direct identity questions, the model's base training wins. The fix (adding `--new` flag, asserting identity in SYSTEM_PROMPT) is present in code but has not been verified to prevent this.

---

**B3 — Greeting/casual input answered with infrastructure docs**

Observed in: session 46ccf9ab

What happens:
- User: "hello Hal, how are you today?"
- Classifier has no "conversational" category → query falls to agentic
- `run_agent()` seeds the first message with KB context (anything scoring ≥ 0.6)
- KB returns Prometheus configuration docs for a greeting
- LLM answers the KB context, not the actual question

Real example:
```
user:      "hello Hal, how are you today?"
assistant: "Based on the information provided:
            1. Prometheus Container Status:
               The Prometheus container is up and running for 3 days..."
```

The intent classifier has no "conversational/chitchat" category. There is no example sentence for "hello", "thanks", "good morning" etc. These all fall to agentic, which unconditionally seeds KB context.

---

**B4 — Agentic loop exhausted without producing an answer**

Observed in: session 834492e3

What happens:
- User: "is everything ok with the lab?"
- Routes to agentic (despite being a health question — classifier misclassification possible)
- Model calls tools repeatedly
- After 8 iterations: "Reached max iterations without a final answer."

The loop-breaking mechanism (dedup + injected "you have all the data" message) did not produce a final text response within 8 iterations.

---

**B5 — Terminal text fed as input to HAL → model tries to execute it**

Observed in: session ef83921a

What happens:
- User pasted a terminal prompt line (`jp@the-lab:~/orion$ hal --new`) into HAL
- Model responded with: `{"name": "run_command", "arguments": {"command": "hal --new"}}`
- User pasted HAL's welcome banner (the Rich panel) → model responded with a KB search for "End-to-end solution for e-commerce search via embedding learning"

These are one-off user errors, but they reveal that the agentic KB seeding can pattern-match bizarre things from terminal output and generate completely wrong tool calls.

---

**B6 — Health question sometimes answered with KB docs instead of live metrics**

Observed in: session c090338a

What happens:
- "hows the lab today?" → should route to health, get live metrics
- Session shows answer is hardware specs and OS info: "The lab server is currently running Fedora Linux 43 with a robust hardware configuration..."
- This is KB content, not Prometheus metrics

Either:
1. The classifier routed to `fact` instead of `health` (threshold boundary), or
2. The classifier routed to `agentic`, KB was seeded, and the LLM answered KB content without calling `get_metrics`

Adjacent session (ddf4eafc, 4 minutes later): same query "hows the lab today?" → correct health metrics response. The classifier result appears inconsistent across restarts (embeddings rebuilt each startup — should be deterministic with the same model, but startup timing/model loading may vary).

---

### What is actually working

- Health routing for clear health queries: works (session ddf4eafc)
- Fact routing for clear fact queries: works when intent is high-confidence
- `run_command` / `read_file` / `list_dir` with Judge gating: no evidence of failures
- Watchdog: firing correctly, cooldown working, logging correctly
- pgvector-kb-api: running, accessible
- Session persistence: saves correctly; search/resume/label all work

---

## STEP 3: Prioritized Diagnosis

These are root causes, not symptoms. Ordered by severity.

---

### RC1 — The model does not reliably emit structured tool calls [CRITICAL]

**What CLAUDE.md says**: agentic loop, LLM calls tools autonomously
**What actually happens**: frequently emits the tool call as a JSON block in `content` instead of via `tool_calls`

The code in `run_agent()` (agent.py:367) checks `msg.get("tool_calls") or []`. When the model outputs JSON text instead of a proper tool call, this is empty — and the JSON dump becomes the "final answer" shown to the user.

This isn't a code bug. The code is correct per the Ollama tool-calling spec. The problem is that `qwen2.5-coder:32b` is a **code completion model** — its tool-calling support via Ollama is unreliable. It knows what tool calls look like (it's seen them in training) so it sometimes just outputs the JSON as text rather than triggering the structured API path.

Evidence it's model-layer: the "tool calls" in the text are themselves plausible (real tool names, real argument structure) but wrong in content (AWS regions for "hello").

**There is no code-level fix for this that isn't a band-aid.** The real fix is either: (a) a model with reliable tool-calling support, or (b) a different architecture that doesn't rely on the model to produce structured output.

---

### RC2 — Model identity is overridden by base training [HIGH]

**What CLAUDE.md says**: system prompt asserts HAL identity
**What actually happens**: on direct identity questions ("what are you?", "do you have a prompt?"), the model reverts to "I'm Qwen, created by Alibaba Cloud"

The SYSTEM_PROMPT instructs the model to be HAL. But `qwen2.5-coder` was RLHF-trained to respond to identity questions with a hardcoded answer. That training beat the system prompt in session 550cae47 on every single exchange.

The current "fix" (asserting identity in SYSTEM_PROMPT + `hal --new` flag) reduces the frequency but does not eliminate this. The `hal --new` flag only helps if the user knows to use it; it's not the default for follow-up sessions.

**This is also a model-layer problem.** It can be mitigated but not eliminated at the system-prompt level with this model.

---

### RC3 — Session history propagates failures into future sessions [HIGH]

**What CLAUDE.md says**: session history is loaded to give HAL memory
**What actually happens**: every broken turn (JSON dumps, Qwen identity responses) is saved to SQLite and re-injected at the start of the next session

There is no pruning. If a session contains 5 turns where HAL called itself Qwen, those 5 turns appear at the top of the next session's context window. The LLM then sees "previous conversations where I was Qwen" and has strong prior to continue as Qwen.

This means RC2 compounds over time: each Qwen-identity session makes the next session more likely to produce Qwen-identity responses.

There is also no upper bound on how old the history injected can be (beyond the 40-turn window) — sessions are resumed by default, so HAL inherits the tail of every previous session.

---

### RC4 — No conversational/chitchat category in intent classifier [MEDIUM]

**What CLAUDE.md says**: classifier routes health / fact / agentic
**What actually happens**: greetings and casual input fall to agentic → KB seeded → LLM answers KB content

"hello", "thanks", "how are you", typos, pasted terminal output — all route to agentic. Agentic seeds whatever KB content scores ≥ 0.6 against the input, which produces bizarre context for the LLM.

This is a design gap, not a bug. Adding a "conversational" intent category that the LLM handles without tools or KB context would fix it cleanly.

---

### RC5 — `run_agent()` KB seeding is unconditional [MEDIUM]

**What CLAUDE.md says**: seeds KB context to help the agent
**What actually happens**: any query with KB score ≥ 0.6 gets that context prepended, whether or not it's relevant

For a casual greeting, the KB returns the closest matching docs (e.g. Prometheus config) regardless of actual relevance. The LLM then anchors on that content.

This is related to RC4 but separate: even if we add a conversational category, other agentic queries may seed irrelevant context. The threshold (0.6) has no backing validation that it represents "actually relevant."

---

### RC6 — `harvest_last_run` missing, but harvest HAS partially run [LOW]

**What CLAUDE.md says**: harvest has never run on server; lab-infrastructure and lab-state categories don't exist yet; 2,244 doc chunks

**What actually exists** (verified with psql now installed):
```
category                          | count
----------------------------------+-------
ai-agents-and-multi-agent-systems |  1440
rag-and-knowledge-retrieval       |   799
lab-infrastructure                |    35     ← exists, harvest was run
lab-state                         |    14     ← exists, harvest was run
ghs-genome                        |     4     ← undocumented, foreign data
ghs-rejections                    |     1     ← undocumented, foreign data
                                  |  2293 total (not 2,244)
```

**What actually happened**: harvest was run at some point, but before the `harvest_last_run` timestamp file was added to the code. So the data is there, but the watchdog can't detect it. The watchdog fires every 30 minutes complaining about a problem that doesn't fully exist.

**Two real issues here**:
1. `harvest_last_run` is missing → fix by running `touch ~/.orion/harvest_last_run` OR running harvest again to refresh the data and write the stamp
2. Foreign data in the KB: `ghs-genome` and `ghs-rejections` (5 rows combined) — these don't belong in a homelab assistant KB. Low harm (5 rows out of 2,293) but should be understood and cleaned.

---

### Tool installation note (completed during session)

`sqlite3` and `psql` CLI tools were missing from the server. Installed via `dnf install sqlite postgresql`.

---

## Appendix: Band-aids and Patches Found in Codebase

These are listed here as reference for the diagnosis step. Not proposing to fix any of them yet.

**P1 — Control token stripping (`_CONTROL_TOKEN_RE`)**
- File: `hal/agent.py` lines 7, 254, 304, 372
- What it does: strips `<|...|>` tokens from all LLM responses in all three handlers
- Why it exists: qwen2.5-coder sometimes emits its own chat template markers (`<|im_start|>`, `<|im_end|>`) in plain text output
- Patch nature: symptom treatment — the model is leaking internal tokens; the code hides them instead of preventing them

**P2 — Loop-breaking user message injection**
- File: `hal/agent.py` lines 415-424
- What it does: when the model calls duplicate tools (all calls are deduped), injects a user message "You already have all the data you need..."
- Why it exists: model loops on the same tool call instead of producing a final answer
- Patch nature: behavioral prompt patch for a stuck-loop failure mode

**P3 — Forced no-tools on final iteration**
- File: `hal/agent.py` line 362
- What it does: passes empty tools list on last iteration to force a text response
- Why it exists: without this, the model can exhaust iterations without ever producing a final answer
- Patch nature: guard rail — not wrong per se, but it exists because the model doesn't reliably self-terminate

**P4 — Tool result format missing `tool_call_id`**
- File: `hal/agent.py` line 409
- What it does: appends `{"role": "tool", "content": result}` to the working history
- OpenAI/Ollama spec: tool results should include `tool_call_id` to correlate with the originating call
- Impact: Qwen via Ollama appears to handle this by position, not ID. But it diverges from spec and may cause subtle multi-call ordering issues if the model makes parallel tool calls.
- Note: this hasn't been observed to cause failures in practice (21/21 tests pass), but tests only cover the intent classifier, not the agent loop

**P5 — Judge `_llm_reason()` system prompt (pending, documented in backlog)**
- File: `hal/judge.py` lines 144-163
- What it does: asks LLM for a risk assessment using `ollama.chat()` — no tools passed, but system prompt doesn't tell it to avoid external data/tool calls
- Risk: if the model somehow tries to generate a tool call in this single `chat()` call, the response might be malformed
- In practice: `chat()` doesn't pass a `tools` schema so the model can't actually call tools. Low real risk.

---

## Watchdog Status (as of session start)

The watchdog has been firing `harvest_lag` every 30 minutes since 13:58:26 today (7 alerts logged). Every alert fails to send to ntfy because `NTFY_URL` is not set in the server `.env`. The log is the only record.

Cooldown mechanism is working correctly — fires every 30 minutes, not every 5.

The fix is one of:
1. Run `python -m harvest` on the server (clears the root cause)
2. Add `NTFY_URL` to server `.env` (enables ntfy delivery — separate issue)
