"""End-to-end autonomy integration tests — Phase D validation.

These tests validate the full self-healing wiring:
  health check tool → agent loop → recovery tool → playbook executor → Judge → executor

Only the LLM, executor, and external endpoints are faked. Judge, dispatch_tool,
run_agent, tool handlers, and playbook logic run as **real code**.

Uses the Scripted LLM pattern from tests/conftest.py (same as test_integration.py).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from conftest import ScriptedExecutor, ScriptedLLM

from hal.agent import run_agent
from hal.healthcheck import ComponentHealth

# ---------------------------------------------------------------------------
# Helpers — build LLM response dicts (same pattern as test_integration.py)
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


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

_ALL_HEALTHY = [
    ComponentHealth("vLLM", "ok", "Qwen2.5-32B-Instruct-AWQ loaded", 142.0),
    ComponentHealth("Ollama", "ok", "nomic-embed-text available", 23.0),
    ComponentHealth("pgvector", "ok", "19847 chunks", 31.0),
    ComponentHealth("Prometheus", "ok", "ready", 12.0),
    ComponentHealth("Containers", "ok", "5/5 running", 5.0),
    ComponentHealth("Pushgateway", "ok", "ready", 8.0),
    ComponentHealth("Grafana", "ok", "ok", 15.0),
    ComponentHealth("ntopng", "ok", "interfaces available", 20.0),
]

_PGVECTOR_DOWN = [
    ComponentHealth("vLLM", "ok", "Qwen2.5-32B-Instruct-AWQ loaded", 142.0),
    ComponentHealth("Ollama", "ok", "nomic-embed-text available", 23.0),
    ComponentHealth("pgvector", "down", "connection refused", 5001.0),
    ComponentHealth("Prometheus", "ok", "ready", 12.0),
    ComponentHealth("Containers", "ok", "5/5 running", 5.0),
    ComponentHealth("Pushgateway", "ok", "ready", 8.0),
    ComponentHealth("Grafana", "ok", "ok", 15.0),
    ComponentHealth("ntopng", "ok", "interfaces available", 20.0),
]


def _mock_config():
    """Build a minimal Config mock for health check tool context."""
    config = MagicMock()
    config.vllm_url = "http://localhost:8000"
    config.ollama_host = "http://localhost:11434"
    config.prometheus_url = "http://localhost:9091"
    config.ntopng_url = "http://localhost:3000"
    config.lab_hostname = "test-lab"
    config.lab_host = "127.0.0.1"
    config.lab_hardware_summary = ""
    config.chat_model = "test-model"
    config.infra_base = "/opt"
    config.tavily_api_key = ""
    return config


# ===========================================================================
# 1 — check_system_health tool through the real agent loop
# ===========================================================================


class TestHealthCheckThroughAgentLoop:
    """check_system_health tool returns structured health data via run_agent."""

    @patch("hal.healthcheck.run_all_checks", return_value=_ALL_HEALTHY)
    def test_health_check_returns_formatted_table(
        self,
        mock_checks,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """LLM calls check_system_health → real handler → formatted table returned."""
        llm = ScriptedLLM(
            [
                _tool_call("check_system_health", {}, call_id="tc_health"),
                _text_response(
                    "All 8 components are healthy. Everything is running normally."
                ),
            ]
        )

        result = run_agent(
            user_input="is everything working?",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=ScriptedExecutor(),
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-health-tool",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # LLM was called at least twice (tool call + text response)
        assert llm.call_count >= 2
        # Verify mock was called
        mock_checks.assert_called_once()
        # The tool result (health table) was fed back to the LLM
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert len(tool_msg) >= 1
        assert "vLLM" in tool_msg[0]["content"]
        assert "ok" in tool_msg[0]["content"]

    @patch("hal.healthcheck.run_all_checks", return_value=_PGVECTOR_DOWN)
    def test_health_check_shows_degraded_components(
        self,
        mock_checks,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """Health check correctly surfaces a down component."""
        llm = ScriptedLLM(
            [
                _tool_call("check_system_health", {}, call_id="tc_health"),
                _text_response("pgvector is down — connection refused."),
            ]
        )

        result = run_agent(
            user_input="system health check",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=ScriptedExecutor(),
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-health-down",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # Tool result contains the "down" status
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("down" in msg["content"] for msg in tool_msg)
        assert any("pgvector" in msg["content"] for msg in tool_msg)

    def test_health_check_without_config_returns_error(
        self,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """check_system_health with no config returns an error message, not a crash."""
        llm = ScriptedLLM(
            [
                _tool_call("check_system_health", {}, call_id="tc_health"),
                _text_response("Health checks are not available in this context."),
            ]
        )

        result = run_agent(
            user_input="health check",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=ScriptedExecutor(),
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-health-noconfig",
            system="You are HAL.",
            console=quiet_console,
            config=None,  # no config
        )

        assert result
        # Tool result mentions unavailability
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("unavailable" in msg["content"].lower() for msg in tool_msg)


# ===========================================================================
# 2 — recover_component tool through the real agent loop
# ===========================================================================


class TestRecoverComponentThroughAgentLoop:
    """recover_component triggers playbook execution via the real wiring."""

    @patch("hal.playbooks.time.sleep")  # skip 1s sleep between step and verify
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")  # don't write state file in tests
    def test_successful_recovery_through_agent(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """LLM calls recover_component → playbook executes → success reported."""
        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
                "docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb": {
                    "stdout": "pgvector-kb:Up 2 seconds",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "pgvector is down"},
                    call_id="tc_recover",
                ),
                _text_response("Successfully restarted pgvector."),
            ]
        )

        # Mock the post-recovery health check called inside _handle_recover_component
        with patch("hal.healthcheck.run_all_checks", return_value=_ALL_HEALTHY):
            result = run_agent(
                user_input="restart pgvector",
                history=[],
                llm=llm,
                kb=stub_kb,
                prom=stub_prom,
                executor=executor,
                judge=auto_approve_judge,
                mem=memory_store,
                session_id="test-recover-ok",
                system="You are HAL.",
                console=quiet_console,
                config=_mock_config(),
            )

        assert result
        # Playbook command was actually executed via the ScriptedExecutor
        assert "docker restart pgvector-kb" in executor.commands_run
        # Verify step also ran
        assert any("docker ps" in cmd for cmd in executor.commands_run)
        # Circuit breaker was checked
        mock_cb.assert_called_once()
        # Tool result reports success
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("successful" in msg["content"].lower() for msg in tool_msg)

    @patch("hal.playbooks.time.sleep")
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")
    def test_recovery_denied_by_judge(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        real_judge,  # auto-denies tier > 0
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """real_judge denies tier-1 playbook steps → executor never called."""
        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "it's down"},
                    call_id="tc_recover",
                ),
                _text_response(
                    "I cannot restart pgvector — requires interactive approval."
                ),
            ]
        )

        result = run_agent(
            user_input="fix pgvector",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=real_judge,
            mem=memory_store,
            session_id="test-recover-deny",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # Executor was never called — Judge denied the tier-1 playbook step
        assert len(executor.commands_run) == 0
        # Tool result mentions denial
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("denied" in msg["content"].lower() for msg in tool_msg)

    def test_recovery_invalid_component(
        self,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """recover_component with an unknown component returns an error, not a crash."""
        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "nonexistent", "reason": "test"},
                    call_id="tc_recover",
                ),
                _text_response("No playbook exists for that component."),
            ]
        )

        result = run_agent(
            user_input="fix nonexistent service",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=ScriptedExecutor(),
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-recover-invalid",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # Tool result mentions "no recovery playbook"
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("no recovery playbook" in msg["content"].lower() for msg in tool_msg)


# ===========================================================================
# 3 — Circuit breaker prevents retry storms
# ===========================================================================


class TestCircuitBreakerIntegration:
    """Circuit breaker blocks recovery when rate limit is exceeded."""

    @patch("hal.playbooks._check_circuit_breaker", return_value=False)
    def test_circuit_breaker_blocks_recovery(
        self,
        mock_cb,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """When circuit breaker is tripped, executor is never called."""
        executor = ScriptedExecutor()

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "down again"},
                    call_id="tc_recover",
                ),
                _text_response(
                    "Recovery is rate-limited — too many attempts this hour."
                ),
            ]
        )

        result = run_agent(
            user_input="restart pgvector again",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-cb-block",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # Executor was never called — circuit breaker prevented it
        assert len(executor.commands_run) == 0
        # Tool result mentions circuit breaker
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("circuit breaker" in msg["content"].lower() for msg in tool_msg)


# ===========================================================================
# 4 — Full detect → diagnose → recover sequence
# ===========================================================================


class TestDetectDiagnoseRecoverLoop:
    """Full sequence: check_system_health → recover_component → report."""

    @patch("hal.playbooks.time.sleep")
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")
    def test_full_detect_recover_sequence(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """LLM detects pgvector down, triggers recovery, reports success."""
        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
                "docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb": {
                    "stdout": "pgvector-kb:Up 2 seconds",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                # Step 1: LLM calls check_system_health — sees pgvector down
                _tool_call("check_system_health", {}, call_id="tc_diag"),
                # Step 2: LLM calls recover_component for pgvector
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "pgvector is down"},
                    call_id="tc_fix",
                ),
                # Step 3: LLM reports the outcome
                _text_response(
                    "pgvector was down. I restarted it and confirmed it's back up."
                ),
            ]
        )

        # First health check call returns pgvector down,
        # post-recovery check returns all healthy
        check_call_count = {"n": 0}
        original_pgvector_down = list(_PGVECTOR_DOWN)
        original_all_healthy = list(_ALL_HEALTHY)

        def _mock_run_all_checks(config, timeout=5):
            check_call_count["n"] += 1
            if check_call_count["n"] == 1:
                return original_pgvector_down
            return original_all_healthy

        with patch("hal.healthcheck.run_all_checks", side_effect=_mock_run_all_checks):
            result = run_agent(
                user_input="pgvector seems down, diagnose and fix it",
                history=[],
                llm=llm,
                kb=stub_kb,
                prom=stub_prom,
                executor=executor,
                judge=auto_approve_judge,
                mem=memory_store,
                session_id="test-full-loop",
                system="You are HAL.",
                console=quiet_console,
                config=_mock_config(),
            )

        assert result
        # LLM was called 3 times (health check, recover, text response)
        assert llm.call_count == 3
        # Playbook command was executed
        assert "docker restart pgvector-kb" in executor.commands_run
        # Health checks were called at least once (diagnostic) and once (post-recovery)
        assert check_call_count["n"] >= 2

    @patch("hal.playbooks.time.sleep")
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")
    def test_detect_recover_with_failed_verification(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """Recovery runs but verify step fails — LLM gets failure detail."""
        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
                # Verify step does NOT contain expected "pgvector-kb:Up"
                "docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb": {
                    "stdout": "pgvector-kb:Exited (1) 3 seconds ago",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "it crashed"},
                    call_id="tc_recover",
                ),
                _text_response("Recovery failed — pgvector didn't come back up."),
            ]
        )

        result = run_agent(
            user_input="restart pgvector",
            history=[],
            llm=llm,
            kb=stub_kb,
            prom=stub_prom,
            executor=executor,
            judge=auto_approve_judge,
            mem=memory_store,
            session_id="test-recover-fail-verify",
            system="You are HAL.",
            console=quiet_console,
            config=_mock_config(),
        )

        assert result
        # The restart command was attempted
        assert "docker restart pgvector-kb" in executor.commands_run
        # Tool result mentions failure
        tool_msg = [c for c in llm.calls[1]["messages"] if c.get("role") == "tool"]
        assert any("failed" in msg["content"].lower() for msg in tool_msg)


# ===========================================================================
# 5 — Trust evolution + recovery interaction
# ===========================================================================


class TestTrustEvolutionRecovery:
    """Trust-promoted playbook steps execute through the full recovery path."""

    @patch("hal.playbooks.time.sleep")
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")
    def test_trust_promoted_recovery_executes(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
        tmp_path,
    ):
        """A trust-promoted Judge auto-approves tier-1 playbook step."""
        audit_log = tmp_path / "audit.log"

        # Pre-populate: 11 successful "docker restart" outcomes → promotes to tier 0
        lines = []
        for _ in range(11):
            entry = {
                "ts": "2026-03-03T00:00:00+00:00",
                "status": "outcome",
                "outcome": "success",
                "action": "run_command",
                "detail": "docker restart pgvector-kb",
            }
            lines.append(json.dumps(entry))
        audit_log.write_text("\n".join(lines) + "\n")

        class AutoDenyJudge:
            """Judge that denies tier>0 UNLESS trust promotes it."""

            def __init__(self):
                from hal.judge import Judge

                class _Inner(Judge):
                    def _request_approval(self, action_type, detail, tier, reason):
                        return False

                self._judge = _Inner(audit_log=audit_log)

            def approve(self, *args, **kwargs):
                return self._judge.approve(*args, **kwargs)

            def record_outcome(self, *args, **kwargs):
                return self._judge.record_outcome(*args, **kwargs)

        judge = AutoDenyJudge()

        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
                "docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb": {
                    "stdout": "pgvector-kb:Up 2 seconds",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "down"},
                    call_id="tc_recover",
                ),
                _text_response("Recovery complete."),
            ]
        )

        with patch("hal.healthcheck.run_all_checks", return_value=_ALL_HEALTHY):
            result = run_agent(
                user_input="fix pgvector",
                history=[],
                llm=llm,
                kb=stub_kb,
                prom=stub_prom,
                executor=executor,
                judge=judge,
                mem=memory_store,
                session_id="test-trust-recover",
                system="You are HAL.",
                console=quiet_console,
                config=_mock_config(),
            )

        assert result
        # Trust promoted tier 1 → 0, so playbook step WAS executed
        assert "docker restart pgvector-kb" in executor.commands_run


# ===========================================================================
# 6 — Audit log records recovery outcomes
# ===========================================================================


class TestRecoveryAuditTrail:
    """Recovery actions are recorded in the audit log for observability."""

    @patch("hal.playbooks.time.sleep")
    @patch("hal.playbooks._check_circuit_breaker", return_value=True)
    @patch("hal.playbooks._record_attempt")
    def test_successful_recovery_logged(
        self,
        mock_record,
        mock_cb,
        mock_sleep,
        auto_approve_judge,
        stub_kb,
        stub_prom,
        memory_store,
        quiet_console,
    ):
        """A successful recovery writes outcome entries to the audit log."""
        executor = ScriptedExecutor(
            {
                "docker restart pgvector-kb": {
                    "stdout": "pgvector-kb",
                    "stderr": "",
                    "returncode": 0,
                },
                "docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb": {
                    "stdout": "pgvector-kb:Up 2 seconds",
                    "stderr": "",
                    "returncode": 0,
                },
            }
        )

        llm = ScriptedLLM(
            [
                _tool_call(
                    "recover_component",
                    {"component": "pgvector", "reason": "crashed"},
                    call_id="tc_recover",
                ),
                _text_response("Done."),
            ]
        )

        with patch("hal.healthcheck.run_all_checks", return_value=_ALL_HEALTHY):
            run_agent(
                user_input="fix pgvector",
                history=[],
                llm=llm,
                kb=stub_kb,
                prom=stub_prom,
                executor=executor,
                judge=auto_approve_judge,
                mem=memory_store,
                session_id="test-audit",
                system="You are HAL.",
                console=quiet_console,
                config=_mock_config(),
            )

        # Read audit log — should contain outcome entries
        audit_path = auto_approve_judge.audit_log
        log_lines = audit_path.read_text().strip().split("\n")
        outcome_entries = [
            json.loads(line) for line in log_lines if '"outcome"' in line
        ]
        # At least one success outcome from the playbook step
        success_entries = [e for e in outcome_entries if e.get("outcome") == "success"]
        assert len(success_entries) >= 1
