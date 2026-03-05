"""Full-circuit integration tests — Scripted LLM pattern.

These tests exercise the connected wiring between HAL's components:
  query → classify → agent loop → tool call → Judge gate → execution → response

Only the LLM and executor are faked.  Judge, dispatch_intent, dispatch_tool,
run_agent, and all tool handlers run as **real code**.

See notes/integration-test-plan.md for the full design rationale.
"""

from __future__ import annotations

import json

from conftest import (
    FakeClassifier,
    ScriptedExecutor,
    ScriptedLLM,
    StubKB,
    StubProm,
)

from hal.agent import run_agent
from hal.bootstrap import dispatch_intent
from hal.judge import Judge, tier_for
from hal.server import ServerJudge

# ---------------------------------------------------------------------------
# Helpers — build LLM response dicts
# ---------------------------------------------------------------------------


def _text_response(text: str) -> dict:
    """Build a text-only LLM response (no tool calls)."""
    return {"role": "assistant", "content": text, "tool_calls": None}


def _tool_call(name: str, args: dict, call_id: str = "tc_001") -> dict:
    """Build a tool-call LLM response."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "function": {"name": name, "arguments": args},
            }
        ],
    }


# ===========================================================================
# Step 1 — Judge Denial Mid-Agent-Loop (Gap 1)
# ===========================================================================


class TestJudgeDenialInAgentLoop:
    """Verify that real Judge denials propagate correctly through run_agent."""

    def test_agent_tool_denied_by_judge_returns_gracefully(
        self,
        real_judge,
        scripted_executor,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """When Judge denies a tier-2 command, the agent should respond
        gracefully and the executor should never be called."""
        llm = ScriptedLLM(
            [
                # Step 1: LLM requests a dangerous command
                _tool_call(
                    "run_command",
                    {"command": "docker run --privileged ubuntu", "reason": "test"},
                ),
                # Step 2: After denial, LLM gives a text response
                _text_response(
                    "I was unable to run that command as it requires approval."
                ),
            ]
        )

        result = run_agent(
            user_input="run a privileged container",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=scripted_executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-denial",
            system="You are HAL.",
            console=quiet_console,
        )

        # Executor was never called
        assert len(scripted_executor.commands_run) == 0
        # Response acknowledges the denial
        assert result  # non-empty
        # Audit log has a denied entry
        audit_log = real_judge.audit_log
        log_lines = audit_log.read_text().strip().split("\n")
        denied_entries = [json.loads(line) for line in log_lines if '"denied"' in line]
        assert len(denied_entries) >= 1

    def test_agent_mixed_approved_and_denied_tools(
        self,
        real_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """Tier-0 tools execute, tier-2 tools are denied, agent handles both."""
        executor = ScriptedExecutor()

        llm = ScriptedLLM(
            [
                # Step 1: search_kb (tier 0 — auto-approved)
                _tool_call("search_kb", {"query": "docker"}, call_id="tc_001"),
                # Step 2: run_command tier 2 (denied)
                _tool_call(
                    "run_command",
                    {"command": "docker run --rm ubuntu echo hi", "reason": "test"},
                    call_id="tc_002",
                ),
                # Step 3: final text response
                _text_response("I found KB results but couldn't run the command."),
            ]
        )

        result = run_agent(
            user_input="search for docker info and run a container",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-mixed",
            system="You are HAL.",
            console=quiet_console,
        )

        # search_kb executed (no executor call needed for KB)
        # run_command was denied — executor was never called
        assert len(executor.commands_run) == 0
        assert result  # non-empty response

    def test_agent_denial_does_not_poison_history(
        self,
        real_judge,
        scripted_executor,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """After a denied tool call, session history contains only clean
        user/assistant turns — no tool artifacts, no 'Action denied' strings."""
        llm = ScriptedLLM(
            [
                _tool_call(
                    "run_command",
                    {"command": "chmod 777 /etc/passwd", "reason": "test"},
                ),
                _text_response("I cannot change permissions on system files."),
            ]
        )

        history: list[dict] = []
        run_agent(
            user_input="make passwd world-writable",
            history=history,
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=scripted_executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-poison",
            system="You are HAL.",
            console=quiet_console,
        )

        # History should have exactly 2 entries: user + assistant
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        # Only user and assistant roles present
        for entry in history:
            assert entry["role"] in ("user", "assistant")


# ===========================================================================
# Step 2 — dispatch_intent() Routing (Gap 2)
# ===========================================================================


class TestDispatchIntentRouting:
    """Verify dispatch_intent routes conversational vs agentic correctly."""

    def test_dispatch_conversational_skips_agent(
        self,
        stub_kb,
        stub_prom,
        scripted_executor,
        real_judge,
        memory_store,
        quiet_console,
    ):
        """Conversational intent skips run_agent entirely — LLM gets tools=[]."""
        llm = ScriptedLLM(
            [
                _text_response("Hello! How can I help you today?"),
            ]
        )

        result = dispatch_intent(
            user_input="hey there",
            history=[],
            llm=llm,
            prom=stub_prom,
            kb=stub_kb,
            executor=scripted_executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-conv",
            system_prompt="You are HAL.",
            console=quiet_console,
            classifier=FakeClassifier("conversational", 0.95),
        )

        assert result == "Hello! How can I help you today?"
        # LLM was called with tools=[] (conversational path)
        assert llm.calls[0]["tools"] == []

    def test_dispatch_health_enters_run_agent(
        self,
        stub_kb,
        stub_prom,
        scripted_executor,
        real_judge,
        memory_store,
        quiet_console,
    ):
        """Health intent enters run_agent (not conversational fast path).
        Stub Prometheus data is pre-seeded, so LLM responds with metrics."""
        llm = ScriptedLLM(
            [
                _text_response(
                    "CPU is at 12.5%, memory at 45%, disk at 38%. All healthy."
                ),
            ]
        )

        result = dispatch_intent(
            user_input="how is the server doing?",
            history=[],
            llm=llm,
            prom=stub_prom,
            kb=stub_kb,
            executor=scripted_executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-health",
            system_prompt="You are HAL.",
            console=quiet_console,
            classifier=FakeClassifier("health", 0.90),
        )

        # Response exists and LLM was called with tools (not empty list)
        assert result
        assert len(llm.calls[0]["tools"]) > 0  # run_agent passes available_tools

    def test_dispatch_without_classifier_always_runs_agent(
        self,
        stub_kb,
        stub_prom,
        scripted_executor,
        real_judge,
        memory_store,
        quiet_console,
    ):
        """When classifier=None, dispatch_intent always routes to run_agent."""
        llm = ScriptedLLM(
            [
                _text_response("Here you go."),
            ]
        )

        result = dispatch_intent(
            user_input="hello",
            history=[],
            llm=llm,
            prom=stub_prom,
            kb=stub_kb,
            executor=scripted_executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-no-clf",
            system_prompt="You are HAL.",
            console=quiet_console,
            classifier=None,
        )

        assert result
        # run_agent was called (tools is non-empty)
        assert len(llm.calls[0]["tools"]) > 0


# ===========================================================================
# Step 3 — ServerJudge Denial Propagation (Gap 3)
# ===========================================================================


class TestServerJudgePropagation:
    """Verify ServerJudge denial flows through run_agent and HTTP endpoints."""

    def test_server_judge_denies_tier1_through_agent(
        self,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """ServerJudge auto-denies tier 1+ commands through the full agent loop."""
        server_judge = ServerJudge(audit_log=tmp_path / "audit.log")

        executor = ScriptedExecutor(
            {
                "docker restart nginx": {
                    "stdout": "nginx",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "run_command",
                    {
                        "command": "docker restart nginx",
                        "reason": "user asked to restart",
                    },
                ),
                _text_response("I cannot restart services over the HTTP interface."),
            ]
        )

        result = run_agent(
            user_input="restart nginx",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=server_judge,
            mem=memory_store,
            session_id="test-server-deny",
            system="You are HAL.",
            console=quiet_console,
        )

        # docker restart is tier 1, ServerJudge denies it
        assert len(executor.commands_run) == 0
        assert result  # non-empty response

    def test_server_judge_allows_tier0_read_only(
        self,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """ServerJudge allows tier-0 tools (search_kb, get_metrics)."""
        server_judge = ServerJudge(audit_log=tmp_path / "audit.log")
        executor = ScriptedExecutor()

        llm = ScriptedLLM(
            [
                _tool_call("search_kb", {"query": "nginx config"}, call_id="tc_001"),
                _text_response("Here's what I found about nginx configuration."),
            ]
        )

        kb = StubKB(
            [
                {
                    "file": "lab.md",
                    "score": 0.85,
                    "content": "nginx runs on port 80",
                }
            ]
        )

        result = run_agent(
            user_input="tell me about nginx config",
            history=[],
            llm=llm,
            kb=kb,
            prom=stub_prom,
            executor=executor,
            judge=server_judge,
            mem=memory_store,
            session_id="test-server-allow",
            system="You are HAL.",
            console=quiet_console,
        )

        assert result  # non-empty — search_kb is tier 0, approved

    def test_server_chat_endpoint_with_real_dispatch(self, tmp_path, monkeypatch):
        """POST /chat with ServerJudge + real dispatch_intent produces a
        graceful response, not raw internal strings."""
        from contextlib import asynccontextmanager
        from unittest.mock import MagicMock

        import hal.memory as _mem

        # Point MemoryStore at a temp database so the server doesn't
        # touch the real ~/.orion/memory.db
        monkeypatch.setattr(_mem, "DB_PATH", tmp_path / "memory.db")

        # Import app and _state after patching.  Replace the lifespan
        # with a no-op so the server doesn't try to connect to vLLM/Ollama.
        from hal.server import _state, app

        @asynccontextmanager
        async def _noop_lifespan(_app):
            yield

        app.router.lifespan_context = _noop_lifespan

        server_judge = ServerJudge(audit_log=tmp_path / "audit.log")

        llm = ScriptedLLM(
            [
                # dispatch_intent → run_agent → LLM tries a tier-1 command
                _tool_call(
                    "run_command",
                    {
                        "command": "systemctl restart docker",
                        "reason": "health check",
                    },
                ),
                _text_response("I cannot restart services over this interface."),
            ]
        )

        # Build a minimal config mock for get_system_prompt() / endpoint usage
        config = MagicMock()
        config.vllm_url = "http://localhost:8000"
        config.ollama_host = "http://localhost:11434"
        config.prometheus_url = "http://localhost:9091"
        config.ntopng_url = "http://localhost:3000"
        config.lab_hostname = "orion"
        config.lab_host = "192.168.5.10"
        config.lab_hardware_summary = ""
        config.chat_model = "test-model"
        config.infra_base = "/opt"
        config.tavily_api_key = ""

        # Pre-populate server state
        _state.clear()
        _state.update(
            {
                "config": config,
                "llm": llm,
                "judge": server_judge,
                "kb": StubKB(),
                "prom": StubProm(),
                "executor": ScriptedExecutor(),
                "classifier": FakeClassifier("agentic", 0.90),
            }
        )

        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/chat", json={"message": "restart docker"})

        assert resp.status_code == 200
        body = resp.json()
        assert "response" in body
        assert body["response"]  # non-empty


# ===========================================================================
# Step 4 — Trust Evolution Integration
# ===========================================================================


class TestTrustEvolution:
    """Verify trust evolution promotes tier-1 commands after proven track record."""

    def test_trust_evolution_promotes_tier1_to_tier0(self, tmp_path):
        """After 10+ successful outcomes, a tier-1 command is auto-approved."""
        audit_log = tmp_path / "audit.log"

        # Pre-populate audit log with 11 successful outcomes for "docker restart"
        # trust_key = "run_command:docker" (first token of the command)
        lines = []
        for _i in range(11):
            entry = {
                "ts": "2026-03-03T00:00:00+00:00",
                "status": "outcome",
                "outcome": "success",
                "action": "run_command",
                "detail": "docker restart nginx",
            }
            lines.append(json.dumps(entry))
        audit_log.write_text("\n".join(lines) + "\n")

        class AutoDenyJudge(Judge):
            def _request_approval(self, action_type, detail, tier, reason):
                return False  # would deny tier 1 if not promoted

        judge = AutoDenyJudge(audit_log=audit_log)

        # "docker restart nginx" is normally tier 1
        assert tier_for("run_command", "docker restart nginx") == 1

        # With trust evolution, approve() should auto-approve (tier reduced to 0)
        result = judge.approve("run_command", "docker restart nginx")
        assert result is True  # promoted to tier 0, auto-approved

    def test_trust_evolution_inside_agent_loop(
        self,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """Trust-promoted command executes through full agent loop even with
        _request_approval=False."""
        audit_log = tmp_path / "audit.log"

        # Pre-populate: 11 successful "docker restart" outcomes
        lines = []
        for _ in range(11):
            entry = {
                "ts": "2026-03-03T00:00:00+00:00",
                "status": "outcome",
                "outcome": "success",
                "action": "run_command",
                "detail": "docker restart nginx",
            }
            lines.append(json.dumps(entry))
        audit_log.write_text("\n".join(lines) + "\n")

        class AutoDenyJudge(Judge):
            def _request_approval(self, action_type, detail, tier, reason):
                return False

        judge = AutoDenyJudge(audit_log=audit_log)

        executor = ScriptedExecutor(
            {
                "docker restart nginx": {
                    "stdout": "nginx",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "run_command",
                    {"command": "docker restart nginx", "reason": "user asked"},
                ),
                _text_response("Successfully restarted nginx."),
            ]
        )

        result = run_agent(
            user_input="restart nginx",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=judge,
            mem=memory_store,
            session_id="test-trust-evo",
            system="You are HAL.",
            console=quiet_console,
        )

        # Trust promoted tier 1 → tier 0, so executor WAS called
        assert "docker restart nginx" in executor.commands_run
        assert result  # non-empty


# ===========================================================================
# Step 5 — EvalJudge Correctness
# ===========================================================================


class TestEvalJudge:
    """Verify EvalJudge records tool attempts and denies destructive commands."""

    def test_eval_judge_records_all_tool_attempts(
        self,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """EvalJudge records every tool the model attempts, approved or not."""
        from eval.run_eval import _EvalJudge

        eval_judge = _EvalJudge(audit_log=tmp_path / "audit.log")

        executor = ScriptedExecutor()

        llm = ScriptedLLM(
            [
                _tool_call("search_kb", {"query": "test"}, call_id="tc_001"),
                _tool_call(
                    "run_command",
                    {"command": "docker stop nginx", "reason": "test"},
                    call_id="tc_002",
                ),
                _text_response("Done."),
            ]
        )

        run_agent(
            user_input="search and stop nginx",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=eval_judge,
            mem=memory_store,
            session_id="test-eval",
            system="You are HAL.",
            console=quiet_console,
        )

        # run_command goes through judge.approve() and is recorded
        assert "run_command" in eval_judge.tools_called
        # search_kb does NOT call judge.approve() (it's a pure KB query),
        # so it won't appear in tools_called — that's correct behaviour.
        # docker stop is tier 1, so EvalJudge denies it — executor never runs.
        assert len(executor.commands_run) == 0

    def test_eval_judge_denies_destructive_commands(
        self,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """EvalJudge silently denies tier 1+ without interactive prompts."""
        from eval.run_eval import _EvalJudge

        eval_judge = _EvalJudge(audit_log=tmp_path / "audit.log")
        executor = ScriptedExecutor()

        llm = ScriptedLLM(
            [
                _tool_call(
                    "run_command",
                    {"command": "rm -rf /tmp/test", "reason": "cleanup"},
                ),
                _text_response("Could not execute that command."),
            ]
        )

        result = run_agent(
            user_input="clean up temp files",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=eval_judge,
            mem=memory_store,
            session_id="test-eval-deny",
            system="You are HAL.",
            console=quiet_console,
        )

        assert len(executor.commands_run) == 0  # never executed
        assert result  # non-empty response
