"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""

import json
import re
import textwrap

from rich.console import Console

from hal.agents import CriticAgent, PlannerAgent
from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import get_logger, set_context
from hal.memory import MemoryStore
from hal.prometheus import Counter, Histogram, PrometheusClient, flush_metrics
from hal.tools import dispatch_tool, get_tools
from hal.tracing import get_tracer

MAX_ITERATIONS = 8
# Max unique tool calls per turn — loop also stops at MAX_ITERATIONS.
MAX_TOOL_CALLS = 5

# Planner/Critic gating: short non-action queries skip sub-agents.
# Keep these explicit and easy to tune.
PLANNER_CRITIC_SHORT_QUERY_WORDS = 7
PLANNER_CRITIC_ACTION_VERBS = frozenset(
    {
        "apply",
        "build",
        "change",
        "check",
        "create",
        "debug",
        "delete",
        "deploy",
        "diagnose",
        "edit",
        "explain",
        "fix",
        "install",
        "investigate",
        "list",
        "patch",
        "reconfigure",
        "reload",
        "remove",
        "repair",
        "restart",
        "rollback",
        "run",
        "scan",
        "search",
        "show",
        "start",
        "stop",
        "troubleshoot",
        "update",
        "verify",
        "write",
    }
)

# Metrics (no-op unless PROM_PUSHGATEWAY is configured)
REQ_TOTAL = Counter("hal_requests_total", labels=("intent", "outcome"))
REQ_LATENCY = Histogram("hal_request_latency_seconds", labels=("intent",))
TOOL_CALLS_TOTAL = Counter("hal_tool_calls_total", labels=("tool", "outcome"))

# Logger
log = get_logger(__name__)


def _strip_tool_artifacts(text: str) -> str:
    """Remove bare tool-call JSON objects leaked into prose response text.

    The model occasionally appends a raw {"name": ..., "arguments": ...} object
    to an otherwise clean prose response instead of issuing it via the structured
    tool_calls field.  These objects are always a B1 error — strip them so they
    never reach the user.

    Uses json.JSONDecoder.raw_decode so nested JSON inside command strings is
    handled correctly.  No-op on clean text.
    """
    decoder = json.JSONDecoder()
    out: list[str] = []
    pos = 0
    while pos < len(text):
        brace = text.find("{", pos)
        if brace == -1:
            out.append(text[pos:])
            break
        # Append verbatim everything before this opening brace.
        out.append(text[pos:brace])
        try:
            obj, end = decoder.raw_decode(text, brace)
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON at this position — keep the character and advance.
            out.append("{")
            pos = brace + 1
            continue
        if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
            # Tool-call artifact — drop it entirely, advance past the object.
            pos = end
        else:
            # Real JSON literal that belongs in the response — keep verbatim.
            out.append(text[brace:end])
            pos = end
    return "".join(out).strip()


def _should_use_planner_critic(query: str) -> tuple[bool, str]:
    """Deterministically decide if Planner/Critic should run.

    Rules:
    - Action-ish query (contains an action verb): use planner/critic.
    - Long query (more than threshold words): use planner/critic.
    - Otherwise (short + non-action): skip planner/critic.
    """
    words = re.findall(r"[a-z0-9']+", query.lower())
    if any(word in PLANNER_CRITIC_ACTION_VERBS for word in words):
        return True, "action_verb"
    if len(words) > PLANNER_CRITIC_SHORT_QUERY_WORDS:
        return True, "long_query"
    return False, "short_non_action"


def run_health(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    prom: PrometheusClient,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Health handler: fetch live metrics, answer in one LLM call with no tools."""
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    with get_tracer().start_as_current_span("hal.run_health") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        set_context(session_id=session_id)
        try:
            with console.status("[dim]fetching metrics...[/]", spinner="dots"):
                h = prom.health()
            metrics_str = "\n".join(f"{k}: {v}" for k, v in h.items() if v is not None)
            span.set_attribute("hal.metrics_available", True)
        except Exception as e:
            metrics_str = f"Metrics unavailable: {e}"
            outcome = "metrics_error"
            span.set_attribute("hal.metrics_available", False)

        messages = list(history) + [
            {
                "role": "user",
                "content": f"Current lab metrics:\n{metrics_str}\n\n{user_input}",
            }
        ]

        try:
            with console.status("[dim]thinking...[/]", spinner="dots"):
                response = llm.chat(messages, system=system)
        except Exception as e:
            outcome = "llm_error"
            response = f"Error calling model: {e}"

        response = response.strip()
        span.set_attribute("hal.response_len", len(response))
        console.print(f"\n[bold cyan]hal>[/] {response}")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response)

        if len(history) > 40:
            history[:] = history[-40:]

    dur = time.perf_counter() - t0
    REQ_LATENCY.observe(dur, intent="health")
    REQ_TOTAL.inc(intent="health", outcome=outcome)
    flush_metrics()
    log.info("health turn", extra={"intent": "health", "confidence": 1.0})
    return response


def run_fact(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    kb: KnowledgeBase,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Fact handler: search KB once, answer in one LLM call with no tools.

    If the KB has nothing relevant, the LLM answers from the system prompt alone
    (which contains key lab facts). If it still doesn't know, it says so.
    """
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    with get_tracer().start_as_current_span("hal.run_fact") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        set_context(session_id=session_id)
        try:
            with console.status("[dim]searching knowledge base...[/]", spinner="dots"):
                chunks = kb.search(user_input, top_k=3)
            relevant = [c for c in chunks if c["score"] >= 0.5]
            span.set_attribute("hal.kb.chunks_returned", len(chunks))
            span.set_attribute("hal.kb.relevant_chunks", len(relevant))
            if relevant:
                span.set_attribute("hal.kb.top_score", relevant[0]["score"])
        except Exception:
            relevant = []
            outcome = "kb_error"
            span.set_attribute("hal.kb.chunks_returned", 0)
            span.set_attribute("hal.kb.relevant_chunks", 0)

        if relevant:
            context = "\n\n".join(
                f"[{c['file']} | score={c['score']:.2f}]\n{c['content'].strip()}"
                for c in relevant
            )
            augmented = f"{context}\n\n{user_input}"
        else:
            augmented = user_input

        messages = list(history) + [{"role": "user", "content": augmented}]

        try:
            with console.status("[dim]thinking...[/]", spinner="dots"):
                response = llm.chat(messages, system=system)
        except Exception as e:
            outcome = "llm_error"
            response = f"Error calling model: {e}"

        response = response.strip()
        span.set_attribute("hal.response_len", len(response))
        console.print(f"\n[bold cyan]hal>[/] {response}")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response)

        if len(history) > 40:
            history[:] = history[-40:]

    dur = time.perf_counter() - t0
    REQ_LATENCY.observe(dur, intent="fact")
    REQ_TOTAL.inc(intent="fact", outcome=outcome)
    flush_metrics()
    log.info("fact turn", extra={"intent": "fact"})
    return response


def run_agent(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    executor: SSHExecutor,
    judge: Judge,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
    ntopng_url: str = "http://localhost:3000",
    tavily_api_key: str = "",
    planner: PlannerAgent | None = None,
    critic: CriticAgent | None = None,
) -> str:
    """Agentic loop: LLM calls tools autonomously until it produces a final answer.

    Returns the final text response.
    """
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    with get_tracer().start_as_current_span("hal.run_agent") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        set_context(session_id=session_id)

        planner_plan = ""
        critic_review = ""

        # Sub-agents: Planner and Critic — only for action-ish/complex queries.
        use_planner_critic, gate_reason = _should_use_planner_critic(user_input)
        span.set_attribute("hal.planner_critic_used", use_planner_critic)
        span.set_attribute("hal.planner_critic_gate_reason", gate_reason)

        if use_planner_critic:
            if planner is None:
                planner = PlannerAgent(llm)
            if critic is None:
                critic = CriticAgent(llm)

            try:
                planner_plan = planner.run(
                    user_input=user_input,
                    history=None,
                    session_id=session_id,
                )
                span.set_attribute("hal.planner_used", bool(planner_plan))
            except Exception as e:
                log.error("planner failed: %s", e, extra={"subagent": "Planner"})
                span.set_attribute("hal.planner_error", True)
                span.set_attribute("hal.planner_used", False)

            if planner_plan:
                try:
                    critic_review = critic.run(
                        user_input=user_input,
                        plan=planner_plan,
                        history=None,
                        session_id=session_id,
                    )
                    span.set_attribute("hal.critic_used", bool(critic_review))
                except Exception as e:
                    log.error("critic failed: %s", e, extra={"subagent": "Critic"})
                    span.set_attribute("hal.critic_error", True)
                    span.set_attribute("hal.critic_used", False)
            else:
                span.set_attribute("hal.critic_skipped", True)
                span.set_attribute("hal.critic_used", False)
        else:
            span.set_attribute("hal.planner_used", False)
            span.set_attribute("hal.critic_used", False)
            span.set_attribute("hal.critic_skipped", True)

        # Seed the first message with KB context (fast, cheap, often helpful)
        # Threshold 0.75: only inject context that is a strong semantic match.
        # At 0.6 casual queries pulled in loosely-related docs (e.g. Prometheus
        # config for a greeting) which the LLM answered instead of the question.
        sections: list[str] = []
        kb_seeded_chunks = 0
        try:
            chunks = kb.search(user_input, top_k=3)
            context_lines = []
            for c in chunks:
                if c["score"] >= 0.75:
                    context_lines.append(f"[{c['file']} | score={c['score']:.2f}]")
                    context_lines.append(c["content"].strip())
            if context_lines:
                context_str = "\n".join(context_lines)
                sections.append("KB context:\n" + context_str)
                kb_seeded_chunks = len(context_lines) // 2
            span.set_attribute("hal.kb.seeded_chunks", kb_seeded_chunks)
        except Exception:
            span.set_attribute("hal.kb.seeded_chunks", 0)

        # Defensive: ensure sub-agent outputs are strings before appending
        if not isinstance(planner_plan, str):
            planner_plan = ""
        if not isinstance(critic_review, str):
            critic_review = ""

        if planner_plan:
            sections.append("Planner's plan:\n" + planner_plan)

        if critic_review:
            sections.append("Critic's review:\n" + critic_review)

        sections.append("User query:\n" + user_input)
        augmented = "\n\n".join(sections)

        # Working history — don't mutate the session history until we have a final answer
        working = list(history) + [{"role": "user", "content": augmented}]

        # Build the active tool set once — only includes tools whose API
        # keys / config are present.  The LLM never sees disabled tools.
        available_tools = get_tools(tavily_api_key=tavily_api_key)

        response_text = ""
        seen_calls: set[tuple] = set()  # (name, args_json) — detect repeat tool calls
        total_calls = 0  # total unique tool calls dispatched this turn

        for iteration in range(MAX_ITERATIONS):
            label = f" (step {iteration + 1})" if iteration > 0 else ""
            # If we've already dispatched max unique tool calls, stop collecting data
            # and force a text-only response regardless of iteration count
            effective_tools = (
                available_tools
                if (iteration < MAX_ITERATIONS - 1 and total_calls < MAX_TOOL_CALLS)
                else []
            )
            with console.status(f"[dim]thinking{label}...[/]", spinner="dots"):
                msg = llm.chat_with_tools(working, effective_tools, system=system)

            working.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # Text-only response — agent is done
                response_text = _strip_tool_artifacts(
                    (msg.get("content") or "").strip()
                )
                span.set_attribute("hal.iterations", iteration + 1)
                span.set_attribute("hal.total_tool_calls", total_calls)
                span.set_attribute("hal.response_len", len(response_text))
                console.print(f"\n[bold cyan]hal>[/] {response_text}")
                break

            # Execute each tool call and feed results back
            new_calls = 0
            for tc in tool_calls:
                call_id = tc.get("id", "")
                fn = tc.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})

                # Some models return arguments as a JSON string instead of a dict
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                # Detect repeat calls — model stuck in a loop
                call_key = (name, json.dumps(raw_args, sort_keys=True))
                if call_key in seen_calls:
                    working.append(
                        {
                            "role": "tool",
                            "content": "[Already called — use the result above.]",
                            "tool_call_id": call_id,
                        }
                    )
                    continue
                seen_calls.add(call_key)

                console.print(
                    f"\n[bold green]⏺[/] [cyan]{name}[/]({_fmt_args(raw_args)})"
                )
                with get_tracer().start_as_current_span("hal.tool_call") as tool_span:
                    tool_span.set_attribute("tool.name", name)
                    tool_span.set_attribute("tool.iteration", iteration)
                    tool_span.set_attribute(
                        "tool.args", json.dumps(raw_args, sort_keys=True)[:500]
                    )
                    try:
                        result = dispatch_tool(
                            name,
                            raw_args,
                            executor,
                            judge,
                            kb,
                            prom,
                            ntopng_url,
                            tavily_api_key,
                        )
                        TOOL_CALLS_TOTAL.inc(tool=name, outcome="ok")
                    except Exception as e:
                        result = f"Tool {name} failed: {e}"
                        TOOL_CALLS_TOTAL.inc(tool=name, outcome="error")
                    tool_span.set_attribute("tool.result_len", len(result))

                # Cap tool output to protect the context window
                _MAX_TOOL_OUTPUT = 8000
                if len(result) > _MAX_TOOL_OUTPUT:
                    omitted = len(result) - _MAX_TOOL_OUTPUT
                    result = result[:_MAX_TOOL_OUTPUT] + f"\n[…{omitted} chars omitted]"

                preview = textwrap.shorten(result, width=140, placeholder="…")
                console.print(f"  [dim]{preview}[/]")

                working.append(
                    {"role": "tool", "content": result, "tool_call_id": call_id}
                )
                new_calls += 1
                total_calls += 1

            # If every call this iteration was a duplicate, the model is looping.
            # Inject a directive to stop collecting data and respond in plain text.
            if new_calls == 0:
                working.append(
                    {
                        "role": "user",
                        "content": (
                            "You already have all the data you need. "
                            "Please provide your final answer now as plain text, "
                            "without calling any more tools."
                        ),
                    }
                )

        else:
            response_text = "Reached max iterations without a final answer."
            outcome = "max_iterations"
            span.set_attribute("hal.iterations", MAX_ITERATIONS)
            span.set_attribute("hal.total_tool_calls", total_calls)
            span.set_attribute("hal.max_iterations_reached", True)
            console.print(f"\n[bold cyan]hal>[/] {response_text}")

        # Persist clean user input + final response to session history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response_text})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response_text)

        if len(history) > 40:
            history[:] = history[-40:]

        dur = time.perf_counter() - t0
        REQ_LATENCY.observe(dur, intent="agent")
        REQ_TOTAL.inc(intent="agent", outcome=outcome)
        flush_metrics()
        log.info("agent turn", extra={"intent": "agent"})
        return response_text


def run_conversational(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
) -> str:
    """Fast path for greetings and small talk — one LLM call, no tools, no KB lookup."""
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    with get_tracer().start_as_current_span("hal.run_conversational") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        set_context(session_id=session_id)
        messages = list(history) + [{"role": "user", "content": user_input}]
        try:
            response = llm.chat(messages, system=system).strip()
        except Exception as e:
            outcome = "llm_error"
            response = f"Error calling model: {e}"
        span.set_attribute("hal.response_len", len(response))
        console.print(f"\n[bold cyan]hal>[/] {response}")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        mem.save_turn(session_id, "user", user_input)
        mem.save_turn(session_id, "assistant", response)
        if len(history) > 40:
            history[:] = history[-40:]
    dur = time.perf_counter() - t0
    REQ_LATENCY.observe(dur, intent="conversational")
    REQ_TOTAL.inc(intent="conversational", outcome=outcome)
    flush_metrics()
    log.info("conversational turn", extra={"intent": "conversational"})
    return response


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "…"
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
