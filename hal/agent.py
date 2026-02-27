"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""

import json
import textwrap

from rich.console import Console

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import get_logger, set_context
from hal.memory import MemoryStore
from hal.prometheus import Counter, Histogram, PrometheusClient, flush_metrics
from hal.sanitize import strip_tool_call_artifacts
from hal.tools import ToolContext, dispatch_tool, get_tools
from hal.tracing import get_tracer

MAX_ITERATIONS = 8
# Max unique tool calls per turn — loop also stops at MAX_ITERATIONS.
MAX_TOOL_CALLS = 5

# Metrics (no-op unless PROM_PUSHGATEWAY is configured)
REQ_TOTAL = Counter("hal_requests_total", labels=("intent", "outcome"))
REQ_LATENCY = Histogram("hal_request_latency_seconds", labels=("intent",))
TOOL_CALLS_TOTAL = Counter("hal_tool_calls_total", labels=("tool", "outcome"))

# Logger
log = get_logger(__name__)


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
) -> str:
    """Agentic loop: LLM calls tools autonomously until it produces a final answer.

    Returns the final text response.
    On LLM failure: prints error, returns error string, does NOT write to history.
    """
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    with get_tracer().start_as_current_span("hal.run_agent") as span:
        span.set_attribute("hal.session_id", session_id)
        span.set_attribute("hal.query", user_input[:200])
        set_context(session_id=session_id)

        # Build the active tool set once — only includes tools whose API
        # keys / config are present.  The LLM never sees disabled tools.
        available_tools = get_tools(tavily_api_key=tavily_api_key)

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

        sections.append("User query:\n" + user_input)
        augmented = "\n\n".join(sections)

        # Working history — don't mutate the session history until we have a final answer
        working = list(history) + [{"role": "user", "content": augmented}]

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
            try:
                with console.status(f"[dim]thinking{label}...[/]", spinner="dots"):
                    msg = llm.chat_with_tools(working, effective_tools, system=system)
            except Exception as e:
                # LLM unavailable — report error but do NOT write to history.
                # Error strings in history corrupt every subsequent turn.
                outcome = "llm_error"
                log.error("LLM call failed: %s", e)
                err = f"LLM unavailable: {e}"
                console.print(f"\n[bold red]hal>[/] {err}")
                dur = time.perf_counter() - t0
                REQ_LATENCY.observe(dur, intent="agent")
                REQ_TOTAL.inc(intent="agent", outcome=outcome)
                flush_metrics()
                return err

            working.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # Text-only response — agent is done
                response_text = strip_tool_call_artifacts(
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
                            ToolContext(
                                executor=executor,
                                judge=judge,
                                kb=kb,
                                prom=prom,
                                ntopng_url=ntopng_url,
                                tavily_api_key=tavily_api_key,
                            ),
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


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "…"
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
