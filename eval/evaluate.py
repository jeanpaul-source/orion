#!/usr/bin/env python3
"""HAL evaluation — scores collected responses on seven metrics.

Reads:  eval/responses.jsonl      (output of run_eval.py)
Writes: eval/results/eval_out.json

.. note:: ClassVar annotations on evaluator classes prevent the
   mutable-default-shared-between-instances bug (ruff RUF012).

Evaluators
----------
no_raw_json          Custom code  — B1: response must not contain raw tool-call JSON
hal_identity         Custom code  — B2: response must not contain "Qwen"/"Alibaba"
intent_accuracy      Custom code  — routing: intent matched expected_intent
web_tool_accuracy    Custom code  — web: web_search called iff web_search_expected==True
no_tool_simulation   Custom code  — response must not narrate tool calls in fenced JSON
response_length      Custom code  — response must be 10-4000 chars (skip min for trivial)
autonomy_quality     Custom code  — autonomy responses must contain specific findings
relevance            Built-in LLM — B3/B6: response relevant to query (needs vLLM)
coherence            Built-in LLM — general: response is coherent natural language

Usage:
    .venv/bin/python -m eval.evaluate
    .venv/bin/python -m eval.evaluate --responses eval/responses.jsonl
    .venv/bin/python -m eval.evaluate --skip-llm-eval   # skip LLM-judge metrics
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import ClassVar

from rich.console import Console
from rich.table import Table

DEFAULT_RESPONSES = Path(__file__).parent / "responses.jsonl"
DEFAULT_OUT = Path(__file__).parent / "results" / "eval_out.json"

console = Console()


# ── Custom code-based evaluators ─────────────────────────────────────────────


class NoRawJsonEvaluator:
    """Detects B1 failure: raw tool-call JSON emitted as response text.

    A passing response (score=1) is clean natural language.
    A failing response (score=0) contains patterns like {"name": ...} or {"arguments": ...}.
    """

    # Patterns that indicate the model printed a tool call schema as text
    _PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r'\{\s*"name"\s*:'),
        re.compile(r'\{\s*"arguments"\s*:'),
        re.compile(r'"function"\s*:.*?"name"\s*:'),
        re.compile(r"<function-name>"),
        re.compile(r"<args-json-object>"),
    ]

    def __call__(self, *, response: str) -> dict:
        is_raw_json = any(p.search(response) for p in self._PATTERNS)
        return {
            "no_raw_json": 0.0 if is_raw_json else 1.0,
        }


class HalIdentityEvaluator:
    """Detects B2 failure: model identifies as Qwen/Alibaba instead of HAL.

    A passing response (score=1) doesn't mention Qwen or Alibaba identity.
    A failing response (score=0) contains identity-overriding phrases.
    """

    _BAD_PHRASES: ClassVar[list[str]] = [
        "i'm qwen",
        "i am qwen",
        "my name is qwen",
        "created by alibaba",
        "alibaba cloud",
        "i was created by alibaba",
        "qwen, created by",
    ]

    def __call__(self, *, response: str) -> dict:
        lower = response.lower()
        violation = any(phrase in lower for phrase in self._BAD_PHRASES)
        return {
            "hal_identity": 0.0 if violation else 1.0,
        }


class IntentAccuracyEvaluator:
    """Checks whether the classifier routed to the expected intent."""

    def __call__(self, *, intent: str, expected_intent: str) -> dict:
        # Skip accuracy check for queries with no expected_intent set
        if not expected_intent or expected_intent == "agentic":
            # Agentic is the fallback for anything — treat as pass
            correct = True
        else:
            correct = intent == expected_intent
        return {
            "intent_accuracy": 1.0 if correct else 0.0,
        }


class WebToolAccuracyEvaluator:
    """Checks web_search tool-routing decisions.

    For rows that carry a ``web_search_expected`` ground-truth:
      - True  → score 1.0 when 'web_search' appears in tools_called, else 0.0
      - False → score 1.0 when 'web_search' is absent from tools_called, else 0.0
    Rows without ``web_search_expected`` (legacy rows) are skipped (score=1.0).
    """

    def __call__(
        self,
        *,
        tools_called: list | str | None = None,
        web_search_expected: bool | str | None = None,
    ) -> dict:
        # web_search_expected absent or null → not applicable, pass
        if web_search_expected is None or web_search_expected == "":
            return {"web_tool_accuracy": 1.0}

        # azure-ai-evaluation may deserialise JSON arrays as strings
        if isinstance(tools_called, str):
            import json as _json

            try:
                tools_called = _json.loads(tools_called)
            except Exception:
                tools_called = []
        if tools_called is None:
            tools_called = []

        # Normalise bool (may arrive as string "true"/"false" from JSONL)
        if isinstance(web_search_expected, str):
            web_search_expected = web_search_expected.lower() == "true"

        used_web = "web_search" in tools_called
        correct = used_web if web_search_expected else not used_web
        return {"web_tool_accuracy": 1.0 if correct else 0.0}


class NoToolSimulationEvaluator:
    """Detects tool-call simulation: LLM narrates a tool call in prose.

    Different from B1 (entire response is raw JSON).  Here the response is
    otherwise-normal prose but contains a fenced JSON block like:

        ```json
        {"name": "get_metrics", "arguments": {}}
        ```

    This matches the exact pattern caught by ``hal/sanitize.py``'s
    ``strip_tool_call_artifacts()`` — but at the eval layer we detect it
    (score 0) rather than strip it.

    Score 1.0 → clean response (no embedded tool-call fences).
    Score 0.0 → response simulates a tool call in prose.
    """

    # Same regex as hal/sanitize.py TOOL_CALL_FENCE_RE — matches fenced JSON
    # blocks whose body is a single JSON object.
    _FENCE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL
    )

    def __call__(self, *, response: str) -> dict:
        for m in self._FENCE_RE.finditer(response):
            try:
                data = json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and "name" in data and "arguments" in data:
                return {"no_tool_simulation": 0.0}
        return {"no_tool_simulation": 1.0}


class ResponseLengthEvaluator:
    """Checks that responses are neither empty nor excessively long.

    Score 0.0 when:
      - Response is under 10 characters (for non-trivial queries) — likely a
        non-answer like "" or "ok".
      - Response exceeds 4000 characters — likely a raw data dump.

    Score 1.0 otherwise.

    Queries tagged ``"trivial": true`` in the JSONL skip the minimum-length
    check (greetings like "thanks" legitimately get short responses).
    """

    _MIN_LENGTH: ClassVar[int] = 10
    _MAX_LENGTH: ClassVar[int] = 4000

    def __call__(
        self,
        *,
        response: str,
        trivial: bool | str | None = None,
    ) -> dict:
        length = len(response)

        # Normalise trivial flag (may arrive as string from JSONL)
        is_trivial = False
        if isinstance(trivial, str):
            is_trivial = trivial.lower() == "true"
        elif isinstance(trivial, bool):
            is_trivial = trivial

        if not is_trivial and length < self._MIN_LENGTH:
            return {"response_length": 0.0}
        if length > self._MAX_LENGTH:
            return {"response_length": 0.0}
        return {"response_length": 1.0}


class AutonomyEvaluator:
    """Validates that autonomy responses contain specific findings.

    For queries with ``failure_case == "autonomy"``, checks that the response
    contains at least one status indicator ("healthy", "degraded", "running",
    etc.) or a known component name.  A generic non-answer like "I'll look
    into that" scores 0.

    Non-autonomy queries always score 1.0 (not applicable).
    """

    _STATUS_WORDS: ClassVar[list[str]] = [
        "healthy",
        "degraded",
        "unhealthy",
        "running",
        "stopped",
        "restarted",
        "recovered",
        "failed",
        "up",
        "down",
        "ok",
        "error",
        "timeout",
        "unreachable",
    ]

    _COMPONENT_NAMES: ClassVar[list[str]] = [
        "vllm",
        "ollama",
        "pgvector",
        "prometheus",
        "grafana",
        "pushgateway",
        "tempo",
        "falco",
        "ntopng",
        "docker",
        "systemd",
        "nginx",
    ]

    def __call__(
        self,
        *,
        response: str,
        failure_case: str | None = None,
    ) -> dict:
        # Only evaluate autonomy queries; everything else passes.
        if not failure_case or failure_case != "autonomy":
            return {"autonomy_quality": 1.0}

        lower = response.lower()
        # Use word-boundary matching to avoid substring false positives
        # (e.g. "ok" matching inside "look").
        has_status = any(
            re.search(rf"\b{re.escape(word)}\b", lower) for word in self._STATUS_WORDS
        )
        has_component = any(name in lower for name in self._COMPONENT_NAMES)

        if has_status or has_component:
            return {"autonomy_quality": 1.0}
        return {"autonomy_quality": 0.0}


# ── Setup ─────────────────────────────────────────────────────────────────────


def _model_config(vllm_url: str, model: str):
    """Build an OpenAI-compatible model config for vLLM."""
    try:
        from azure.ai.evaluation import OpenAIModelConfiguration

        return OpenAIModelConfiguration(
            type="openai",
            model=model,
            base_url=f"{vllm_url.rstrip('/')}/v1",
            api_key=os.environ.get("VLLM_API_KEY", "not-needed"),
        )
    except ImportError:
        return None


def _build_llm_evaluators(model_config):
    """Return built-in LLM-judge evaluators, or an empty dict if unavailable."""
    try:
        from azure.ai.evaluation import CoherenceEvaluator, RelevanceEvaluator

        return {
            "relevance": RelevanceEvaluator(model_config=model_config),
            "coherence": CoherenceEvaluator(model_config=model_config),
        }
    except ImportError as e:
        console.print(f"[yellow]Could not load built-in LLM evaluators: {e}[/]")
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HAL evaluator")
    parser.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--skip-llm-eval",
        action="store_true",
        help="Skip RelevanceEvaluator and CoherenceEvaluator (no vLLM needed)",
    )
    args = parser.parse_args(argv)

    if not args.responses.exists():
        console.print(
            f"[red]responses.jsonl not found at {args.responses}[/]\n"
            "Run [bold].venv/bin/python -m eval.run_eval[/] first."
        )
        sys.exit(1)

    try:
        # PF_LOGGING_LEVEL must be set before this import: promptflow creates
        # bulk_logger = get_logger("execution.bulk") at module level and reads
        # PF_LOGGING_LEVEL at logger-construction time. Setting it afterward has
        # no effect. setdefault so operator can override with PF_LOGGING_LEVEL=DEBUG.
        os.environ.setdefault("PF_LOGGING_LEVEL", "WARNING")
        from azure.ai.evaluation import evaluate
    except ImportError:
        console.print(
            "[red]azure-ai-evaluation is not installed.[/]\n"
            "Run: [bold].venv/bin/pip install azure-ai-evaluation[/]"
        )
        sys.exit(1)

    # ── Evaluator setup ───────────────────────────────────────────────────────
    evaluators: dict = {
        "no_raw_json": NoRawJsonEvaluator(),
        "hal_identity": HalIdentityEvaluator(),
        "intent_accuracy": IntentAccuracyEvaluator(),
        "web_tool_accuracy": WebToolAccuracyEvaluator(),
        "no_tool_simulation": NoToolSimulationEvaluator(),
        "response_length": ResponseLengthEvaluator(),
        "autonomy_quality": AutonomyEvaluator(),
    }

    evaluator_config: dict = {
        "no_raw_json": {"response": "${data.response}"},
        "hal_identity": {"response": "${data.response}"},
        "intent_accuracy": {
            "intent": "${data.intent}",
            "expected_intent": "${data.expected_intent}",
        },
        "web_tool_accuracy": {
            "tools_called": "${data.tools_called}",
            "web_search_expected": "${data.web_search_expected}",
        },
        "no_tool_simulation": {"response": "${data.response}"},
        "response_length": {
            "response": "${data.response}",
            "trivial": "${data.trivial}",
        },
        "autonomy_quality": {
            "response": "${data.response}",
            "failure_case": "${data.failure_case}",
        },
    }

    if not args.skip_llm_eval:
        import hal.config as cfg

        config = cfg.load()
        model_cfg = _model_config(config.vllm_url, config.chat_model)
        if model_cfg is None:
            console.print(
                "[yellow]azure-ai-evaluation not available — skipping LLM evaluators[/]"
            )
        else:
            llm_evals = _build_llm_evaluators(model_cfg)
            for name, ev in llm_evals.items():
                evaluators[name] = ev
                evaluator_config[name] = {
                    "query": "${data.query}",
                    "response": "${data.response}",
                }
            if llm_evals:
                console.print(
                    f"[dim]LLM evaluators (judge: {config.chat_model} @ {config.vllm_url}): "
                    f"{', '.join(llm_evals)}[/]"
                )
    else:
        console.print("[dim]--skip-llm-eval: skipping relevance/coherence[/]")

    # ── Run evaluation ────────────────────────────────────────────────────────
    args.out.parent.mkdir(parents=True, exist_ok=True)
    console.print(
        f"\nRunning {len(evaluators)} evaluator(s) on [bold]{args.responses}[/]..."
    )

    results = evaluate(
        data=str(args.responses),
        evaluators=evaluators,
        evaluator_config=evaluator_config,
        output_path=str(args.out),
    )

    # ── Summary table ─────────────────────────────────────────────────────────
    # azure.ai.evaluation returns rows as flat dicts with dotted keys, e.g.:
    #   "inputs.query", "inputs.failure_case", "outputs.no_raw_json.no_raw_json"
    # Do NOT use row.get("outputs", {}) — that always returns {} on these rows.
    rows = results.get("rows", [])
    metrics = results.get("metrics", {})

    console.print(f"\n[bold cyan]── Aggregate scores ({len(rows)} queries) ──[/]")
    agg_table = Table(show_header=True, header_style="bold")
    agg_table.add_column("Metric", style="cyan")
    agg_table.add_column("Score (0-1)", justify="right")
    agg_table.add_column("Pass rate", justify="right")

    metric_names = [k for k in metrics if not k.endswith("_reason")]
    for metric_key in sorted(metric_names):
        score = metrics[metric_key]
        pct = f"{score * 100:.1f}%"
        color = "green" if score >= 0.9 else ("yellow" if score >= 0.7 else "red")
        agg_table.add_row(metric_key, f"{score:.3f}", f"[{color}]{pct}[/]")
    console.print(agg_table)

    # ── Per-failure-case breakdown ─────────────────────────────────────────────
    # Rows use flat dotted keys: "inputs.failure_case", "outputs.X.metric_name"
    failures_by_case: dict[str, list[dict]] = {}
    for row in rows:
        fc = row.get("inputs.failure_case") or "unknown"
        query = row.get("inputs.query") or ""
        response = row.get("inputs.response") or ""

        failed_metrics = []
        for k, v in row.items():
            if not k.startswith("outputs."):
                continue
            if k.endswith("_reason"):
                continue
            if isinstance(v, (int, float)) and v < 1.0:
                # Strip "outputs.<evaluator>." prefix → short name, e.g. "no_raw_json"
                short = k.split(".", 2)[-1] if k.count(".") >= 2 else k
                failed_metrics.append(f"{short}={v:.2f}")

        if failed_metrics:
            failures_by_case.setdefault(fc, []).append(
                {
                    "query": query[:60],
                    "response_preview": response[:60].replace("\n", " "),
                    "failed": ", ".join(failed_metrics),
                }
            )

    # ── Unambiguous run status ────────────────────────────────────────────────
    total_scoring_failures = sum(len(v) for v in failures_by_case.values())
    if total_scoring_failures == 0:
        console.print(f"\n[bold green]✓ Scoring failures: 0 / {len(rows)} queries[/]")
    else:
        console.print(
            f"\n[bold red]✗ Scoring failures: {total_scoring_failures} / {len(rows)} queries[/]"
        )
        for fc, items in sorted(failures_by_case.items()):
            console.print(f"\n  [bold]{fc}[/] ({len(items)} failed)")
            for item in items:
                console.print(f"    [dim]Q:[/] {item['query']}")
                console.print(f"    [dim]R:[/] {item['response_preview']}")
                console.print(f"    [red]{item['failed']}[/]")

    console.print(f"\nFull results → [bold]{args.out}[/]")


if __name__ == "__main__":
    main()
