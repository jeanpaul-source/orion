# Plan: RC/P Findings — Verified State and Remaining Work

Created: 2026-03-01
Status: all items complete

---

## Verified State

Produced by reading SESSION_FINDINGS.md in full, then reading the current code for every
finding. Status reflects what is in the code on 2026-03-01 — not what the docs say.

---

### RC1 — Model does not reliably emit structured tool calls

SESSION_FINDINGS verdict: critical, model-layer, no code fix possible.
Current code verdict: root cause resolved by model switch; residual guards are appropriate.

The original observation was against qwen2.5-coder:32b via the Ollama chat API. That backend
and model are gone. The system now uses VLLMClient hitting vLLM at port 8000 with
Qwen/Qwen2.5-32B-Instruct-AWQ via the OpenAI-compatible /v1/chat/completions endpoint. This
model/API pair has reliable structured tool call support.

Current code state:
- llm.py chat_with_tools() returns the full choices[0]["message"] dict. The tool_calls field
  is populated when the model issues tool calls.
- agent.py line 154: tool_calls = msg.get("tool_calls") or [] — unchanged, but vLLM+Qwen2.5-
  32B reliably populates this field via structured generation constraints.
- sanitize.py strip_tool_call_artifacts() is an output guard for any residual leakage.
- memory.py is_poison_response() delegates to is_tool_call_artifact() in sanitize.py,
  preventing artifact turns from persisting to SQLite.

_CONTROL_TOKEN_RE (P1 in SESSION_FINDINGS) is GONE from the entire codebase — only present
in SESSION_FINDINGS.md as a historical reference. The vLLM model does not emit <|im_start|>
or <|im_end|> tokens in content output.

Residual guard rails that are now legitimate design (not band-aids):
- agent.py "if new_calls == 0" user-message injection (P2 in SESSION_FINDINGS): present at
  the end of the tool dispatch loop. Fires when every call in a batch is a duplicate: injects
  "You already have all the data you need." This is correct agent loop design, not a workaround.
- agent.py no-tools on final iteration (P3): now expressed as
  `iteration < MAX_ITERATIONS - 1 and total_calls < MAX_TOOL_CALLS`. Correct loop termination.

P4 (missing tool_call_id) is resolved: every tool result includes "tool_call_id": call_id.

No remaining actionable work for RC1. P1 and P4 are resolved.

---

### RC2 — Model identity overridden by base training

SESSION_FINDINGS verdict: model-layer, mitigable but not eliminable.
Current code verdict: mitigations strengthened; residual risk acceptable; not testable offline.

bootstrap.py get_system_prompt() (line 49 area) now opens with:
  "You are HAL — the intelligence layer of a personal homelab. You are not Qwen, Claude, or
  any other model. You are HAL. Never break this identity. If asked who made you or what model
  you are, say you are HAL, an AI assistant built for this homelab. Do not name or hint at the
  underlying model, provider, or company."

The RULES section includes: "Never simulate a tool call or fabricate shell/command output..."

The model switch from qwen2.5-coder:32b (code model with strong RLHF for Qwen self-
identification) to Qwen2.5-32B-Instruct-AWQ (general instruction model) meaningfully reduces
the probability of identity override on direct questions.

Cannot verify without live vLLM inference. No remaining code-level work for RC2.

---

### RC3 — Session history propagates failures into future sessions

SESSION_FINDINGS verdict: high severity; compounds RC2 over time.
Current code verdict: resolved.

Three mitigations in place and verified in code:
1. memory.py save_turn() calls is_poison_response(content) before writing assistant turns.
   Catches bare JSON objects and fenced tool-call blocks via sanitize.py.
2. run_agent() and _handle_conversational() both check for LLM exceptions and return early
   WITHOUT writing to history. Both have the comment "Error strings in history corrupt every
   subsequent turn."
3. prune_old_turns(days=30) runs at startup; TURN_WINDOW = 40 caps context per session.

No remaining code-level work for RC3.

---

### RC4 — No conversational category in intent classifier

SESSION_FINDINGS verdict: design gap; greetings fall to agentic.
Current code verdict: fully resolved.

intent.py EXAMPLES["conversational"] has 30 entries covering hi, hello, thanks, ok, bye, etc.
bootstrap.py dispatch_intent() routes to _handle_conversational() when intent == "conversational".
_handle_conversational() uses tools=[], no KB lookup, no Prometheus query.

No remaining work.

---

### RC5 — Agentic KB seeding is unconditional

SESSION_FINDINGS verdict: threshold at 0.6 pulls loosely-related docs.
Current code verdict: threshold raised; new unconditional Prometheus pre-seed intentionally added.

agent.py lines 67–76: chunks fetched with kb.search(user_input, top_k=3). Only chunks with
c["score"] >= 0.75 are injected. The 0.6 threshold from SESSION_FINDINGS was already raised.

New behavior (Track A refactor, not in SESSION_FINDINGS): every run_agent() call
unconditionally pre-seeds a Prometheus health snapshot. This is intentional — health queries
now enter run_agent() instead of a dedicated _handle_health(), and the pre-seed ensures they
resolve in iteration 1 without a tool call. If Prometheus is unreachable the pre-seed silently
skips. This is a design decision, not a defect.

No remaining code-level work for RC5.

---

### RC6 — harvest_last_run missing

SESSION_FINDINGS verdict: watchdog fires false alerts.
Current code verdict: resolved in code. Server state not verifiable from repo.

harvest.timer is deployed (ops/harvest.timer, 3:00am daily). harvest/main.py writes
~/.orion/harvest_last_run after each successful run. watchdog.py checks this file's mtime.
The SESSION_FINDINGS issue was a one-time catch from before the timestamp write was added.
After the first post-fix harvest run the file exists. If still missing on the server, run
python -m harvest once. No code work needed.

---

### P5 — Judge _llm_reason() system prompt

SESSION_FINDINGS verdict: risk if model generates tool calls in the risk-assessment call.
Current code verdict: resolved.

judge.py _llm_reason() system prompt now says "Respond with plain text only — do not call any
tools or fetch external data." VLLMClient.chat() (not chat_with_tools()) is called so no tools
schema is passed. P5 is resolved.

---

### NEW FINDING — ARCHITECTURE.md describes stale 4-route dispatch

What ARCHITECTURE.md says:
  conversational -> _handle_conversational()
  health         -> _handle_health()    <- does not exist
  fact           -> _handle_fact()       <- does not exist
  agentic        -> run_agent()

What the code actually does:
bootstrap.py dispatch_intent() has exactly two branches:
1. intent == "conversational" -> _handle_conversational() (no tools, no KB, one LLM call)
2. everything else -> run_agent() (full tool loop, KB+Prometheus pre-seeded)

There is no _handle_health() or _handle_fact(). They were deleted in the Track A routing
refactor (commit 359b55e, "feat(routing): binary dispatch + metrics pre-seed in run_agent").
The rationale is documented in notes/track-a-routing-refactor-plan.md: the health/fact
handlers used tools=[] which caused boundary queries to get shallow answers.

run_agent() now pre-seeds both KB context (at 0.75 threshold) and a live Prometheus snapshot
before iteration 0. Simple queries resolve in one iteration from context; complex queries can
call tools.

This is a documentation-only issue. The code is correct. ARCHITECTURE.md is wrong.
copilot-instructions.md already has a note about this discrepancy.

---

### NEW FINDING — trust_metrics.py is blind to outcome entries

What ROADMAP says: "trust_metrics.py already parses the log; it just needs outcome tracking
wired in."

What the code actually has:

judge.py record_outcome() appends entries like:
  {"ts": "...", "status": "outcome", "outcome": "success", "action": "run_command", "detail": "..."}

judge.py _load_trust_overrides() reads exactly these entries (checks entry.get("status") ==
"outcome") and builds a tier override table. The trust evolution mechanism IS complete and
working inside judge.py.

trust_metrics.py _parse_json_line() line ~138:
  status = _STATUS_NORMALIZE.get(status, status)
  if status not in ("auto", "approved", "denied"):
      return None

The string "outcome" is not in that tuple so ALL outcome entries are silently dropped.

get_action_stats() (the tool exposed to the agent, registered in hal/tools.py) therefore
shows: how many times a tool was called, how many were approved vs denied — but NOT whether
those calls actually succeeded or failed.

An operator who asks "has systemctl restart been working reliably?" gets approval data but no
execution outcome data. The data is in the audit log; the tool does not surface it.

The ROADMAP statement that trust_metrics.py already parses the log is partially correct but
misleading — it parses approval entries, not outcome entries. These are two different populations
of the same file.

---

## Problem Statement

Two items require implementation work:

Item A: ARCHITECTURE.md is factually wrong about routing. It describes four handler functions,
two of which no longer exist. Any engineer or AI context window reading it to understand the
system will have a wrong mental model that diverges from the code in a non-trivial way.

Item B: trust_metrics.py outcome blindness. The get_action_stats tool available in the agent
and via REPL shows only approval history. Outcome entries are filtered out at the parser. The
operator cannot get a meaningful answer to "has this action been working?" even though the
audit log has the data. The ROADMAP says this is "wired in" but it is not.

---

## Relevant Code Locations

Item A — ARCHITECTURE.md update:
- ARCHITECTURE.md "Component map" section: four-route diagram
- ARCHITECTURE.md "Data flow per query" section: health and fact paths
- ARCHITECTURE.md "Intent routing — design rationale": explains health/fact as distinct paths
- hal/bootstrap.py dispatch_intent() line ~277: the actual two-branch implementation
- hal/bootstrap.py _handle_conversational() line ~253: the one specialized handler
- hal/agent.py lines 67–120: KB pre-seed + Prometheus pre-seed inside run_agent()
- notes/track-a-routing-refactor-plan.md: full rationale for the Track A refactor

Item B — trust_metrics.py outcome extension:
- hal/trust_metrics.py line ~138: _parse_json_line() — the filter that drops outcome entries
- hal/trust_metrics.py line ~40–55: AuditEvent dataclass — no outcome field
- hal/trust_metrics.py line ~167–232: aggregate_stats() and CounterStats — no success/fail tracking
- hal/trust_metrics.py line ~240–303: get_action_stats() — return dict has no outcome ratio
- hal/judge.py line ~555–615: record_outcome() — writes entries that trust_metrics.py ignores
- hal/judge.py line ~497–535: _load_trust_overrides() — CORRECT reference implementation for
  reading outcome entries; this is the model for what trust_metrics.py should do

---

## Constraints

Item A (doc update):
- ARCHITECTURE.md sections that are still accurately described must not be changed: LLM backend
  split (vLLM vs Ollama), Judge tier system, memory/observability, KB pipeline, security stack.
- The two-path routing description must explain why the refactor happened so it reads as an
  intentional improvement, not a regression from three paths to two.
- No test changes required for a doc-only update.
- CLAUDE.md maintenance rule: update in place, never append session blocks.

Item B (trust_metrics outcome):
- AuditEvent is a frozen dataclass. Adding an outcome field needs Optional[str] = None to stay
  backward-compatible with approval/denial entries that have no outcome field.
- _parse_json_line filter currently rejects entries where status is not in
  ("auto", "approved", "denied"). Extending to accept "outcome" requires a code path that builds
  an appropriate AuditEvent variant.
- get_action_stats() return schema is used by the get_action_stats tool in hal/tools.py. Adding
  new fields is backward-compatible. Changing or removing existing fields is not.
- Tests in tests/test_trust_metrics.py cover load_audit_log, aggregate_stats, get_action_stats.
  Read that file before touching trust_metrics.py. Any schema change requires test updates.
- CLAUDE.md: propose before acting, one change at a time, run pytest to verify each change.

Test suite: pytest tests/test_trust_metrics.py tests/test_judge.py tests/test_judge_hardening.py

---

## Open Questions

Item A only:
- Should ARCHITECTURE.md retain a note on why health/fact routes were collapsed (for historical
  context) or describe only current state? Recommendation: describe current state only; the
  rationale lives in notes/track-a-routing-refactor-plan.md.
[Decision Made for Item A]
- only current state
  
1. Should outcome entries be parsed into a distinct Python type (OutcomeEvent separate from
   AuditEvent) or should AuditEvent grow an optional outcome field handling both cases?
   Distinct types are cleaner; a unified type is simpler for aggregation.
[Decision Made for (1)]
- need more information

1. Should get_action_stats() return outcome data as a new top-level field in the existing
   return dict, or should a separate get_outcome_stats() function be added? The agent tool
   interface currently exposes only get_action_stats — changing its schema also requires
   updating the tool description in hal/tools.py.
2. The logic in judge.py _load_trust_overrides() correctly reads outcome entries. Should
   trust_metrics.py share that logic, duplicate it, or call into it? Sharing risks coupling
   the analytics module to the judge's internal function; duplication risks drift.

---

## Suggested Sequence

Item A first — documentation change, no code dependencies, one commit.
Item B second — code change requiring: (1) extend parser, (2) update AuditEvent or add type,
(3) extend aggregate/get_action_stats with outcome data, (4) update tool description if schema
changes, (5) update tests. Each sub-step is its own proposal+approval+commit.

Do not combine A and B in one commit per CLAUDE.md rule.
