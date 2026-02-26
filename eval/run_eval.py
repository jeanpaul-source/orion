#!/usr/bin/env python3
"""HAL evaluation runner — drives HAL's handlers with test queries and saves responses.

Reads:  eval/queries.jsonl
Writes: eval/responses.jsonl  (input to evaluate.py)

Usage:
    .venv/bin/python -m eval.run_eval
    .venv/bin/python -m eval.run_eval --queries eval/queries.jsonl --out eval/responses.jsonl

Safety:
    - Commands are blocked by EvalJudge (all tier > 0 actions auto-denied, no prompts)
    - Executor stub returns a placeholder string if a command somehow reaches it
    - A fresh throwaway session is created so eval turns don't appear in real memory
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rich.console import Console

# ── HAL imports ─────────────────────────────────────────────────────────────
import hal.config as cfg
from hal.agent import run_agent, run_conversational, run_fact, run_health
from hal.executor import SSHExecutor
from hal.intent import IntentClassifier
from hal.judge import Judge, tier_for
from hal.knowledge import KnowledgeBase
from hal.llm import OllamaClient, VLLMClient
from hal.main import get_system_prompt
from hal.memory import MemoryStore
from hal.prometheus import PrometheusClient
from hal.tracing import setup_tracing

DEFAULT_QUERIES = Path(__file__).parent / "queries.jsonl"
DEFAULT_OUT = Path(__file__).parent / "responses.jsonl"

console = Console(stderr=True)  # progress to stderr so stdout stays clean


# ── Safety shims ─────────────────────────────────────────────────────────────


class _MockExecutor(SSHExecutor):
    """Never runs anything — returns a stub result for every command."""

    def run(self, command: str) -> dict:  # type: ignore[override]
        return {
            "stdout": "[eval mode: command execution is disabled]",
            "stderr": "",
            "returncode": 0,
        }


class _EvalJudge(Judge):
    """Auto-approves tier-0 (read-only) and silently denies everything else.

    No interactive prompts. No LLM risk evaluation (avoids extra latency).
    Records every tool the model attempts to call in ``tools_called`` so the
    evaluator can check whether web_search / fetch_url were used correctly.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tools_called: list[str] = []

    def reset_tools(self) -> None:
        """Clear the accumulator between queries."""
        self.tools_called = []

    def approve(
        self,
        action_type: str,
        detail: str,
        tier: int | None = None,
        reason: str = "",
    ) -> bool:
        if tier is None:
            tier = tier_for(action_type, detail)
        approved = tier == 0
        # Record every tool the model attempted, approved or not
        self.tools_called.append(action_type)
        self._log(
            action_type,
            detail,
            tier,
            approved=approved,
            auto=True,
            reason=f"eval:{reason}",
        )
        return approved


# ── Runner ────────────────────────────────────────────────────────────────────


def _load_queries(path: Path) -> list[dict]:
    queries = []
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                queries.append(json.loads(line))
            except json.JSONDecodeError as e:
                console.print(f"[yellow]queries.jsonl line {lineno}: skipped ({e})[/]")
    return queries


def _run_query(
    query: str,
    classifier: IntentClassifier,
    llm: VLLMClient,
    embed: OllamaClient,
    kb: KnowledgeBase,
    prom: PrometheusClient,
    executor: _MockExecutor,
    judge: _EvalJudge,
    mem: MemoryStore,
    session_id: str,
    system: str,
) -> tuple[str, str, float, list[str]]:
    """Returns (response_text, intent, confidence, tools_called)."""
    # Each query gets a clean history — no cross-contamination between queries
    history: list[dict] = []
    judge.reset_tools()
    intent, confidence = classifier.classify(query)
    quiet = Console(quiet=True)

    if intent == "health":
        response = run_health(query, history, llm, prom, mem, session_id, system, quiet)
    elif intent == "fact":
        response = run_fact(query, history, llm, kb, mem, session_id, system, quiet)
    elif intent == "conversational":
        response = run_conversational(
            query, history, llm, mem, session_id, system, quiet
        )
    else:
        response = run_agent(
            query,
            history,
            llm,
            kb,
            prom,
            executor,
            judge,
            mem,
            session_id,
            system,
            quiet,
        )

    return response, intent, confidence, list(judge.tools_called)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HAL eval runner")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first error instead of continuing",
    )
    args = parser.parse_args(argv)

    # Eval output should stay readable even when no OTLP collector is running.
    # Allow explicit operator override by honoring pre-set OTEL_SDK_DISABLED.
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    setup_tracing()
    _tracing_disabled = os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true"
    if _tracing_disabled:
        console.print("[dim]Tracing: disabled (OTEL_SDK_DISABLED=true)[/]")
    else:
        _otlp = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318")
        console.print(f"[dim]Tracing: enabled → {_otlp}[/]")

    queries = _load_queries(args.queries)
    if not queries:
        console.print("[red]No queries found. Exiting.[/]")
        sys.exit(1)

    console.print(f"[cyan]Loaded {len(queries)} queries from {args.queries}[/]")

    config = cfg.load()
    console.print(f"[dim]vLLM: {config.vllm_url}  Ollama: {config.ollama_host}[/]")

    # Build clients
    llm = VLLMClient(config.vllm_url, config.chat_model)
    if not llm.ping():
        console.print(
            f"[red]vLLM not responding at {config.vllm_url}. Is it running?[/]"
        )
        sys.exit(1)

    embed = OllamaClient(config.ollama_host, config.embed_model)
    if not embed.ping():
        console.print(f"[red]Ollama not responding at {config.ollama_host}.[/]")
        sys.exit(1)

    kb = KnowledgeBase(config.pgvector_dsn, embed)
    prom = PrometheusClient(config.prometheus_url)
    executor = _MockExecutor(config.lab_host, config.lab_user)
    judge = _EvalJudge(
        llm=None, audit_log=Path("/dev/null")
    )  # no LLM risk eval; sink audit
    mem = MemoryStore()

    # Fresh throwaway session — won't interfere with real sessions
    session_id = mem.new_session()
    mem.conn.execute("UPDATE sessions SET label=? WHERE id=?", ("eval-run", session_id))
    mem.conn.commit()

    console.print("[dim]Building intent classifier...[/]")
    classifier = IntentClassifier(embed)

    SYSTEM = get_system_prompt()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    errors = 0

    with args.out.open("w") as out_f:
        for i, item in enumerate(queries, 1):
            query = item["query"]
            console.print(
                f"[bold]({i}/{len(queries)})[/] [dim]{item.get('failure_case', '')}[/] {query[:80]}"
            )
            try:
                response, intent, confidence, tools_called = _run_query(
                    query,
                    classifier,
                    llm,
                    embed,
                    kb,
                    prom,
                    executor,
                    judge,
                    mem,
                    session_id,
                    SYSTEM,
                )
                row = {
                    "query": query,
                    "response": response,
                    "intent": intent,
                    "confidence": round(confidence, 4),
                    "expected_intent": item.get("expected_intent", ""),
                    "failure_case": item.get("failure_case", ""),
                    "description": item.get("description", ""),
                    "tools_called": tools_called,
                    "web_search_expected": item.get("web_search_expected"),
                }
                out_f.write(json.dumps(row) + "\n")
                out_f.flush()
                results.append(row)
                console.print(
                    f"  intent={intent} ({confidence:.2f})  "
                    f"tools={tools_called}  "
                    f"response={len(response)}c  preview: {response[:60].replace(chr(10), ' ')!r}"
                )
            except Exception as exc:
                errors += 1
                console.print(f"  [red]ERROR: {exc}[/]")
                if args.fail_fast:
                    raise
                # Write an error row so the row count stays aligned with queries
                row = {
                    "query": query,
                    "response": f"[RUNNER ERROR: {exc}]",
                    "intent": "error",
                    "confidence": 0.0,
                    "expected_intent": item.get("expected_intent", ""),
                    "failure_case": item.get("failure_case", ""),
                    "description": item.get("description", ""),
                    "tools_called": [],
                    "web_search_expected": item.get("web_search_expected"),
                }
                out_f.write(json.dumps(row) + "\n")
                out_f.flush()

    mem.close()

    console.print(
        f"\n[green]Done.[/] {len(results)} responses written to [bold]{args.out}[/]"
        + (f"  [yellow]{errors} errors[/]" if errors else "")
    )
    console.print("Next step: [bold].venv/bin/python -m eval.evaluate[/]")


if __name__ == "__main__":
    main()
