"""Agentic loop — LLM calls tools autonomously, Judge gates everything."""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from hal.executor import ExecutorRegistry
from hal.judge import Judge
from hal.knowledge import KnowledgeBase
from hal.llm import VLLMClient
from hal.logging_utils import get_logger, set_context
from hal.memory import MemoryStore
from hal.prometheus import Counter, Histogram, PrometheusClient, flush_metrics
from hal.sanitize import strip_cjk_lines, strip_tool_call_artifacts
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


# ---------------------------------------------------------------------------
# Structured result — behaves like a string so all existing callers/tests
# continue to work, but carries structured step metadata for the Web UI.
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Return type for run_agent / dispatch_intent.

    Behaves like a ``str`` for backward compatibility (``==``, ``in``,
    ``.lower()``, ``str()``), while carrying an optional ``steps`` list
    that the HTTP API serialises for the Web UI.
    """

    response: str
    steps: list[dict[str, Any]] = field(default_factory=list)

    # -- string protocol for backward compat with existing tests/callers --

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.response == other
        if isinstance(other, AgentResult):
            return self.response == other.response
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.response)

    def __contains__(self, item: str) -> bool:  # type: ignore[override]
        return item in self.response

    def __str__(self) -> str:
        return self.response

    def __repr__(self) -> str:
        return f"AgentResult(response={self.response!r}, steps={len(self.steps)})"

    def __bool__(self) -> bool:
        return bool(self.response)

    def lower(self) -> str:
        return self.response.lower()

    def strip(self, chars: str | None = None) -> str:
        return self.response.strip(chars)

    def startswith(self, prefix: str | tuple[str, ...], *args: int) -> bool:
        return self.response.startswith(prefix, *args)


def run_agent(
    user_input: str,
    history: list[dict],
    llm: VLLMClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    registry: ExecutorRegistry,
    judge: Judge,
    mem: MemoryStore,
    session_id: str,
    system: str,
    console: Console,
    ntopng_url: str = "http://localhost:3000",
    tavily_api_key: str = "",
    config: object | None = None,
) -> AgentResult:
    """Agentic loop: LLM calls tools autonomously until it produces a final answer.

    Returns AgentResult (str-like with .steps metadata).
    On LLM failure: prints error, returns AgentResult with error, does NOT write to history.
    """
    import time

    t0 = time.perf_counter()
    outcome = "ok"
    steps: list[dict[str, Any]] = []
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
            if kb_seeded_chunks > 0:
                steps.append({"type": "kb_seed", "chunks": kb_seeded_chunks})
        except Exception:
            span.set_attribute("hal.kb.seeded_chunks", 0)

        # Seed the first message with a live Prometheus metrics snapshot.
        # Symmetric to the KB pre-seed above: one cheap HTTP call, result injected
        # into the augmented context before the first LLM invocation.
        # why: health-classified queries now enter run_agent (Track A routing refactor).
        # Pre-seeding means simple status questions ("how's CPU?") still resolve in
        # iteration 1 with no tool call — same quality as the old _handle_health path
        # but without forfeiting tool access for boundary queries that need it.
        # If Prometheus is unreachable, we skip silently; run_agent can call get_metrics
        # as a tool on iteration 1 and explain the outage itself.
        def _fmt_metric(val: object, suffix: str = "") -> str:
            return f"{val}{suffix}" if val is not None else "unavailable"

        try:
            _metrics = prom.health()
            if _metrics:
                _snapshot = (
                    f"cpu={_fmt_metric(_metrics.get('cpu_pct'), '%')} "
                    f"mem={_fmt_metric(_metrics.get('mem_pct'), '%')} "
                    f"disk_root={_fmt_metric(_metrics.get('disk_root_pct'), '%')} "
                    f"disk_docker={_fmt_metric(_metrics.get('disk_docker_pct'), '%')} "
                    f"disk_data={_fmt_metric(_metrics.get('disk_data_pct'), '%')} "
                    f"swap={_fmt_metric(_metrics.get('swap_pct'), '%')} "
                    f"load={_fmt_metric(_metrics.get('load1'))} "
                    f"gpu_vram={_fmt_metric(_metrics.get('gpu_vram_pct'), '%')} "
                    f"gpu_temp={_fmt_metric(_metrics.get('gpu_temp_c'), '\u00b0C')}"
                )
                sections.append("Live metrics: " + _snapshot)
                steps.append({"type": "metrics_seed", "snapshot": _snapshot})
                span.set_attribute("hal.metrics.seeded", True)
        except Exception:
            span.set_attribute("hal.metrics.seeded", False)

        sections.append("User query:\n" + user_input)
        augmented = "\n\n".join(sections)

        # Working history — don't mutate the session history until we have a final answer
        working = [*history, {"role": "user", "content": augmented}]

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
                return AgentResult(response=err, steps=steps)

            working.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # Text-only response — agent is done
                response_text = strip_cjk_lines(
                    strip_tool_call_artifacts((msg.get("content") or "").strip())
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
                    _tool_detail = json.dumps(raw_args, sort_keys=True)[:500]
                    try:
                        result = dispatch_tool(
                            name,
                            raw_args,
                            ToolContext(
                                registry=registry,
                                judge=judge,
                                kb=kb,
                                prom=prom,
                                ntopng_url=ntopng_url,
                                tavily_api_key=tavily_api_key,
                                config=config,
                            ),
                        )
                        TOOL_CALLS_TOTAL.inc(tool=name, outcome="ok")
                        if judge:
                            judge.record_outcome(name, _tool_detail, "success")
                    except Exception as e:
                        result = f"Tool {name} failed: {e}"
                        TOOL_CALLS_TOTAL.inc(tool=name, outcome="error")
                        if judge:
                            judge.record_outcome(name, _tool_detail, "error")
                    tool_span.set_attribute("tool.result_len", len(result))

                # Cap tool output to protect the context window
                _MAX_TOOL_OUTPUT = 8000
                if len(result) > _MAX_TOOL_OUTPUT:
                    omitted = len(result) - _MAX_TOOL_OUTPUT
                    result = result[:_MAX_TOOL_OUTPUT] + f"\n[…{omitted} chars omitted]"

                preview = textwrap.shorten(result, width=140, placeholder="…")
                console.print(f"  [dim]{preview}[/]")

                steps.append(
                    {
                        "type": "tool_call",
                        "name": name,
                        "args": raw_args,
                        "result": preview,
                        "iteration": iteration,
                    }
                )

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
        return AgentResult(response=response_text, steps=steps)


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "…"
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)
