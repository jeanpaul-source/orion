#!/usr/bin/env python3
"""HAL evaluation — scores collected responses on four metrics.

Reads:  eval/responses.jsonl      (output of run_eval.py)
Writes: eval/results/eval_out.json

Evaluators
----------
no_raw_json      Custom code  — B1: response must not contain raw tool-call JSON
hal_identity     Custom code  — B2: response must not contain "Qwen"/"Alibaba"
intent_accuracy  Custom code  — routing: intent matched expected_intent
relevance        Built-in LLM — B3/B6: response relevant to query (needs vLLM)
coherence        Built-in LLM — general: response is coherent natural language

Usage:
    .venv/bin/python -m eval.evaluate
    .venv/bin/python -m eval.evaluate --responses eval/responses.jsonl
    .venv/bin/python -m eval.evaluate --skip-llm-eval   # skip LLM-judge metrics
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

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
    _PATTERNS = [
        re.compile(r'\{\s*"name"\s*:'),
        re.compile(r'\{\s*"arguments"\s*:'),
        re.compile(r'"function"\s*:.*?"name"\s*:'),
        re.compile(r'<function-name>'),
        re.compile(r'<args-json-object>'),
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

    _BAD_PHRASES = [
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
        "--skip-llm-eval", action="store_true",
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
    }

    evaluator_config: dict = {
        "no_raw_json": {"response": "${data.response}"},
        "hal_identity": {"response": "${data.response}"},
        "intent_accuracy": {
            "intent": "${data.intent}",
            "expected_intent": "${data.expected_intent}",
        },
    }

    if not args.skip_llm_eval:
        import hal.config as cfg
        config = cfg.load()
        model_cfg = _model_config(config.vllm_url, config.chat_model)
        if model_cfg is None:
            console.print("[yellow]azure-ai-evaluation not available — skipping LLM evaluators[/]")
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
    rows = results.get("rows", [])
    metrics = results.get("metrics", {})

    console.print(f"\n[bold cyan]── Aggregate scores ({len(rows)} queries) ──[/]")
    agg_table = Table(show_header=True, header_style="bold")
    agg_table.add_column("Metric", style="cyan")
    agg_table.add_column("Score (0–1)", justify="right")
    agg_table.add_column("Pass rate", justify="right")

    metric_names = [k for k in metrics if not k.endswith("_reason")]
    for metric_key in sorted(metric_names):
        score = metrics[metric_key]
        pct = f"{score * 100:.1f}%"
        color = "green" if score >= 0.9 else ("yellow" if score >= 0.7 else "red")
        agg_table.add_row(metric_key, f"{score:.3f}", f"[{color}]{pct}[/]")
    console.print(agg_table)

    # ── Per-failure-case breakdown ─────────────────────────────────────────────
    # Group rows by failure_case and show which ones have score < 1
    failures_by_case: dict[str, list[dict]] = {}
    for row in rows:
        outputs = row.get("outputs", {})
        fc = row.get("inputs", {}).get("failure_case", "unknown")
        query = row.get("inputs", {}).get("query", "")
        response = row.get("inputs", {}).get("response", "")

        failed_metrics = []
        for k, v in outputs.items():
            if k.endswith("_reason"):
                continue
            if isinstance(v, (int, float)) and v < 1.0:
                failed_metrics.append(f"{k}={v:.2f}")

        if failed_metrics:
            failures_by_case.setdefault(fc, []).append({
                "query": query[:60],
                "response_preview": response[:60].replace("\n", " "),
                "failed": ", ".join(failed_metrics),
            })

    if failures_by_case:
        console.print("\n[bold red]── Failures by failure case ──[/]")
        for fc, items in sorted(failures_by_case.items()):
            console.print(f"\n  [bold]{fc}[/] ({len(items)} failed)")
            for item in items:
                console.print(f"    [dim]Q:[/] {item['query']}")
                console.print(f"    [dim]R:[/] {item['response_preview']}")
                console.print(f"    [red]{item['failed']}[/]")
    else:
        console.print("\n[bold green]No failures detected.[/]")

    console.print(f"\nFull results → [bold]{args.out}[/]")


if __name__ == "__main__":
    main()
