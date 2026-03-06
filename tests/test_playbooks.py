"""Tests for hal.playbooks — recovery playbook data model, executor, and circuit breaker."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hal.playbooks import (
    COMPONENT_NAMES,
    PLAYBOOKS,
    RecoveryPlaybook,
    RecoveryStep,
    _check_circuit_breaker,
    _load_recovery_state,
    _record_attempt,
    _save_recovery_state,
    execute_playbook,
    get_all_playbooks,
    get_playbook,
)

# ---------------------------------------------------------------------------
# C1 — Data model and registry
# ---------------------------------------------------------------------------


class TestPlaybookDataModel:
    """Validate playbook structure and registry completeness."""

    def test_all_playbooks_have_required_fields(self) -> None:
        for pb in PLAYBOOKS:
            assert pb.name, f"Playbook missing name: {pb}"
            assert pb.component, f"Playbook missing component: {pb}"
            assert pb.trigger in ("down", "degraded"), f"Bad trigger: {pb.trigger}"
            assert pb.description, f"Playbook missing description: {pb}"
            assert pb.judge_tier >= 0, f"Bad judge_tier: {pb.judge_tier}"
            assert pb.max_attempts_per_hour > 0, f"Bad max_attempts: {pb}"
            assert len(pb.steps) > 0, f"Playbook has no steps: {pb.name}"

    def test_all_steps_have_required_fields(self) -> None:
        for pb in PLAYBOOKS:
            for step in pb.steps:
                assert step.description, f"Step missing description in {pb.name}"
                assert step.command, f"Step missing command in {pb.name}"
                assert step.verify_command, f"Step missing verify_command in {pb.name}"
                assert step.verify_expect, f"Step missing verify_expect in {pb.name}"
                assert step.timeout > 0, f"Step bad timeout in {pb.name}"

    def test_all_components_exist_in_health_check_registry(self) -> None:
        """Verify every playbook component matches a health check name."""
        from hal.healthcheck import HEALTH_CHECKS

        health_check_names = {name for name, _fn in HEALTH_CHECKS}
        for pb in PLAYBOOKS:
            assert pb.component in health_check_names, (
                f"Playbook '{pb.name}' references component '{pb.component}' "
                f"not in HEALTH_CHECKS: {health_check_names}"
            )

    def test_playbook_names_are_unique(self) -> None:
        names = [pb.name for pb in PLAYBOOKS]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_component_names_frozenset(self) -> None:
        assert isinstance(COMPONENT_NAMES, frozenset)
        assert len(COMPONENT_NAMES) > 0

    def test_docker_restarts_are_tier_1(self) -> None:
        docker_playbooks = [
            pb for pb in PLAYBOOKS if "docker restart" in pb.steps[0].command
        ]
        for pb in docker_playbooks:
            assert pb.judge_tier == 1, (
                f"{pb.name} should be tier 1, got {pb.judge_tier}"
            )

    def test_vllm_restart_is_tier_1(self) -> None:
        pb = get_playbook("vLLM", "down")
        assert pb is not None
        assert pb.judge_tier == 1

    def test_ollama_restart_is_tier_2(self) -> None:
        pb = get_playbook("Ollama", "down")
        assert pb is not None
        assert pb.judge_tier == 2

    def test_dataclasses_are_frozen(self) -> None:
        step = RecoveryStep(
            description="test",
            command="echo hi",
            verify_command="echo ok",
            verify_expect="ok",
        )
        with pytest.raises(AttributeError):
            step.command = "changed"  # type: ignore[misc]

        pb = PLAYBOOKS[0]
        with pytest.raises(AttributeError):
            pb.name = "changed"  # type: ignore[misc]


class TestGetPlaybook:
    """Test playbook lookup."""

    def test_lookup_existing_playbook(self) -> None:
        pb = get_playbook("pgvector", "down")
        assert pb is not None
        assert pb.name == "restart_pgvector"

    def test_lookup_missing_component(self) -> None:
        assert get_playbook("nonexistent", "down") is None

    def test_lookup_wrong_trigger(self) -> None:
        assert get_playbook("pgvector", "degraded") is None

    def test_get_all_playbooks(self) -> None:
        all_pb = get_all_playbooks()
        assert len(all_pb) == len(PLAYBOOKS)
        assert all_pb is not PLAYBOOKS  # returns a copy


# ---------------------------------------------------------------------------
# C2 — Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Test circuit breaker state management."""

    def test_load_empty_state(self, tmp_path: Path) -> None:
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            state = _load_recovery_state()
            assert state == {}

    def test_save_and_load_state(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            state = {"test_playbook": ["2026-03-05T10:00:00+00:00"]}
            _save_recovery_state(state)
            loaded = _load_recovery_state()
            assert loaded == state

    def test_circuit_breaker_allows_first_attempt(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            pb = RecoveryPlaybook(
                name="test_pb",
                component="test",
                trigger="down",
                description="test",
                judge_tier=1,
                max_attempts_per_hour=3,
                steps=(),
            )
            assert _check_circuit_breaker(pb) is True

    def test_circuit_breaker_trips_at_limit(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        now = datetime.now(UTC)
        timestamps = [
            (now - timedelta(minutes=i)).isoformat(timespec="seconds") for i in range(3)
        ]
        state_file.write_text(json.dumps({"test_pb": timestamps}))
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            pb = RecoveryPlaybook(
                name="test_pb",
                component="test",
                trigger="down",
                description="test",
                judge_tier=1,
                max_attempts_per_hour=3,
                steps=(),
            )
            assert _check_circuit_breaker(pb) is False

    def test_circuit_breaker_prunes_old_entries(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        now = datetime.now(UTC)
        old_ts = (now - timedelta(hours=2)).isoformat(timespec="seconds")
        recent_ts = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
        state_file.write_text(json.dumps({"test_pb": [old_ts, old_ts, recent_ts]}))
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            pb = RecoveryPlaybook(
                name="test_pb",
                component="test",
                trigger="down",
                description="test",
                judge_tier=1,
                max_attempts_per_hour=3,
                steps=(),
            )
            # Only 1 recent entry, limit is 3 → allowed
            assert _check_circuit_breaker(pb) is True

    def test_record_attempt(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            pb = RecoveryPlaybook(
                name="test_pb",
                component="test",
                trigger="down",
                description="test",
                judge_tier=1,
                max_attempts_per_hour=3,
                steps=(),
            )
            _record_attempt(pb)
            state = _load_recovery_state()
            assert len(state["test_pb"]) == 1


# ---------------------------------------------------------------------------
# C2 — Playbook executor
# ---------------------------------------------------------------------------


class TestPlaybookExecutor:
    """Test execute_playbook with mocked executor and judge."""

    @pytest.fixture
    def mock_executor(self) -> MagicMock:
        executor = MagicMock()
        executor.run.return_value = {
            "returncode": 0,
            "stdout": "pgvector-kb:Up 5 minutes\n",
            "stderr": "",
        }
        return executor

    @pytest.fixture
    def mock_judge(self) -> MagicMock:
        judge = MagicMock()
        judge.approve.return_value = True
        judge.record_outcome = MagicMock()
        return judge

    @pytest.fixture
    def sample_playbook(self) -> RecoveryPlaybook:
        return RecoveryPlaybook(
            name="test_restart",
            component="pgvector",
            trigger="down",
            description="Test restart",
            judge_tier=1,
            max_attempts_per_hour=3,
            steps=(
                RecoveryStep(
                    description="Restart container",
                    command="docker restart pgvector-kb",
                    verify_command="docker ps --filter name=pgvector-kb",
                    verify_expect="pgvector-kb:Up",
                    timeout=30,
                ),
            ),
        )

    @patch("hal.playbooks.time.sleep")
    def test_successful_execution(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is True
            assert result.steps_completed == 1
            assert "successfully" in result.detail
            mock_judge.approve.assert_called_once()
            mock_judge.record_outcome.assert_called_once_with(
                "run_command", "docker restart pgvector-kb", "success"
            )

    @patch("hal.playbooks.time.sleep")
    def test_judge_denies_step(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_judge.approve.return_value = False
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is False
            assert result.steps_completed == 0
            assert "denied by Judge" in result.detail

    @patch("hal.playbooks.time.sleep")
    def test_execution_failure(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_executor.run.return_value = {
            "returncode": 1,
            "stdout": "",
            "stderr": "container not found",
        }
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is False
            assert "exit code 1" in result.detail
            mock_judge.record_outcome.assert_called_with(
                "run_command", "docker restart pgvector-kb", "error"
            )

    @patch("hal.playbooks.time.sleep")
    def test_verification_failure(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        # First call (execute) succeeds, second call (verify) returns wrong output
        mock_executor.run.side_effect = [
            {"returncode": 0, "stdout": "ok", "stderr": ""},
            {"returncode": 0, "stdout": "pgvector-kb:Exited", "stderr": ""},
        ]
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is False
            assert "verification failed" in result.detail

    @patch("hal.playbooks.time.sleep")
    def test_circuit_breaker_blocks_execution(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        state_file = tmp_path / "state.json"
        now = datetime.now(UTC)
        timestamps = [
            (now - timedelta(minutes=i)).isoformat(timespec="seconds") for i in range(3)
        ]
        state_file.write_text(json.dumps({"test_restart": timestamps}))
        with patch("hal.playbooks.RECOVERY_STATE_FILE", state_file):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is False
            assert "Circuit breaker" in result.detail
            # Judge should not have been called
            mock_judge.approve.assert_not_called()

    @patch("hal.playbooks.time.sleep")
    def test_executor_exception(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_executor.run.side_effect = TimeoutError("command timed out")
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.success is False
            assert "execution failed" in result.detail

    @patch("hal.playbooks.time.sleep")
    def test_multi_step_playbook_partial_failure(
        self,
        mock_sleep: MagicMock,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A two-step playbook where step 1 succeeds but step 2 fails."""
        pb = RecoveryPlaybook(
            name="multi_step",
            component="test",
            trigger="down",
            description="Multi-step test",
            judge_tier=1,
            max_attempts_per_hour=3,
            steps=(
                RecoveryStep(
                    description="Step 1",
                    command="echo step1",
                    verify_command="echo ok",
                    verify_expect="ok",
                ),
                RecoveryStep(
                    description="Step 2",
                    command="echo step2",
                    verify_command="echo fail",
                    verify_expect="success",  # won't match
                ),
            ),
        )
        mock_executor.run.side_effect = [
            {"returncode": 0, "stdout": "step1", "stderr": ""},
            {"returncode": 0, "stdout": "ok", "stderr": ""},  # verify step 1
            {"returncode": 0, "stdout": "step2", "stderr": ""},
            {
                "returncode": 0,
                "stdout": "fail",
                "stderr": "",
            },  # verify step 2 — no "success"
        ]
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(pb, mock_executor, mock_judge)
            assert result.success is False
            assert result.steps_completed == 1
            assert "verification failed" in result.detail

    @patch("hal.playbooks.time.sleep")
    def test_playbook_result_includes_name(
        self,
        mock_sleep: MagicMock,
        sample_playbook: RecoveryPlaybook,
        mock_executor: MagicMock,
        mock_judge: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch("hal.playbooks.RECOVERY_STATE_FILE", tmp_path / "state.json"):
            result = execute_playbook(sample_playbook, mock_executor, mock_judge)
            assert result.playbook_name == "test_restart"
