"""Recovery playbooks — declarative remediation sequences for HAL components.

Each playbook describes a series of shell commands to diagnose and recover
a failed component, along with verification steps to confirm recovery.
A circuit breaker prevents retry storms.

Design principles:
- Playbooks are data, not code — easy to audit and extend.
- Each step's command goes through the Judge for approval.
- Circuit breaker tracks attempts per playbook per hour.
- Outcomes feed trust evolution via ``Judge.record_outcome()``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from hal.executor import SSHExecutor
    from hal.judge import Judge


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryStep:
    """A single step in a recovery playbook."""

    description: str  # human-readable step description
    command: str  # shell command to execute
    verify_command: str  # command to verify the step succeeded
    verify_expect: str  # expected substring in verify output
    timeout: int = 30  # seconds


@dataclass(frozen=True)
class RecoveryPlaybook:
    """A complete recovery sequence for a component."""

    name: str  # e.g. "restart_pgvector"
    component: str  # matches ComponentHealth.name from healthcheck.py
    trigger: str  # "down" or "degraded"
    description: str  # human-readable description
    judge_tier: int  # what tier this recovery needs
    max_attempts_per_hour: int  # circuit breaker limit
    steps: tuple[RecoveryStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlaybookResult:
    """Outcome of a playbook execution attempt."""

    success: bool
    steps_completed: int
    detail: str
    playbook_name: str = ""


# ---------------------------------------------------------------------------
# Recovery state (circuit breaker persistence)
# ---------------------------------------------------------------------------

RECOVERY_STATE_FILE = Path.home() / ".orion" / "recovery_state.json"


def _load_recovery_state() -> dict[str, list[str]]:
    """Load recovery attempt timestamps from disk.

    Returns ``{playbook_name: [iso_timestamp, ...]}``.
    """
    try:
        return cast(dict[str, list[str]], json.loads(RECOVERY_STATE_FILE.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_recovery_state(state: dict[str, list[str]]) -> None:
    RECOVERY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY_STATE_FILE.write_text(json.dumps(state, indent=2))


def _check_circuit_breaker(playbook: RecoveryPlaybook) -> bool:
    """Return True if the playbook is allowed to run (circuit breaker not tripped).

    Prunes timestamps older than 1 hour, then checks whether the remaining
    count is below ``playbook.max_attempts_per_hour``.
    """
    state = _load_recovery_state()
    timestamps = state.get(playbook.name, [])
    now = datetime.now(UTC)

    # Prune entries older than 1 hour
    recent: list[str] = []
    for ts_str in timestamps:
        try:
            ts = datetime.fromisoformat(ts_str)
            if (now - ts).total_seconds() < 3600:
                recent.append(ts_str)
        except (ValueError, TypeError):
            continue

    # Persist the pruned list
    state[playbook.name] = recent
    _save_recovery_state(state)

    return len(recent) < playbook.max_attempts_per_hour


def _record_attempt(playbook: RecoveryPlaybook) -> None:
    """Record a recovery attempt timestamp for circuit breaker tracking."""
    state = _load_recovery_state()
    timestamps = state.get(playbook.name, [])
    timestamps.append(datetime.now(UTC).isoformat(timespec="seconds"))
    state[playbook.name] = timestamps
    _save_recovery_state(state)


# ---------------------------------------------------------------------------
# Playbook executor
# ---------------------------------------------------------------------------


def execute_playbook(
    playbook: RecoveryPlaybook,
    executor: SSHExecutor,
    judge: Judge,
) -> PlaybookResult:
    """Execute a recovery playbook with circuit breaker and Judge gating.

    Sequence for each step:
    1. Judge.approve() the command
    2. Execute via SSHExecutor
    3. Run verify_command
    4. Check verify_expect in output
    5. Record outcome

    Returns a ``PlaybookResult`` with success/failure detail.
    """
    # Circuit breaker check
    if not _check_circuit_breaker(playbook):
        return PlaybookResult(
            success=False,
            steps_completed=0,
            detail=f"Circuit breaker tripped: {playbook.name} exceeded "
            f"{playbook.max_attempts_per_hour} attempts/hour",
            playbook_name=playbook.name,
        )

    _record_attempt(playbook)
    completed = 0

    for i, step in enumerate(playbook.steps):
        # Gate through Judge
        reason = f"Recovery playbook '{playbook.name}' step {i + 1}: {step.description}"
        if not judge.approve("run_command", step.command, reason=reason):
            judge.record_outcome(
                "run_command",
                step.command,
                "error",
            )
            return PlaybookResult(
                success=False,
                steps_completed=completed,
                detail=f"Step {i + 1} denied by Judge: {step.description}",
                playbook_name=playbook.name,
            )

        # Execute the step
        try:
            result = executor.run(step.command, timeout=step.timeout)
        except Exception as exc:
            judge.record_outcome("run_command", step.command, "error")
            return PlaybookResult(
                success=False,
                steps_completed=completed,
                detail=f"Step {i + 1} execution failed: {exc}",
                playbook_name=playbook.name,
            )

        if result["returncode"] != 0:
            stderr = result["stderr"].strip()
            judge.record_outcome("run_command", step.command, "error")
            return PlaybookResult(
                success=False,
                steps_completed=completed,
                detail=f"Step {i + 1} returned exit code {result['returncode']}: {stderr}",
                playbook_name=playbook.name,
            )

        # Brief pause before verification to let the service start
        time.sleep(1)

        # Verify the step
        try:
            verify_result = executor.run(step.verify_command, timeout=step.timeout)
            output = verify_result["stdout"] + verify_result["stderr"]
            if step.verify_expect not in output:
                judge.record_outcome("run_command", step.command, "error")
                return PlaybookResult(
                    success=False,
                    steps_completed=completed,
                    detail=f"Step {i + 1} verification failed: "
                    f"expected '{step.verify_expect}' not found in output",
                    playbook_name=playbook.name,
                )
        except Exception as exc:
            judge.record_outcome("run_command", step.command, "error")
            return PlaybookResult(
                success=False,
                steps_completed=completed,
                detail=f"Step {i + 1} verification error: {exc}",
                playbook_name=playbook.name,
            )

        judge.record_outcome("run_command", step.command, "success")
        completed += 1

    return PlaybookResult(
        success=True,
        steps_completed=completed,
        detail=f"All {completed} steps completed successfully",
        playbook_name=playbook.name,
    )


# ---------------------------------------------------------------------------
# Playbook registry
# ---------------------------------------------------------------------------

PLAYBOOKS: list[RecoveryPlaybook] = [
    RecoveryPlaybook(
        name="restart_pgvector",
        component="pgvector",
        trigger="down",
        description="Restart the pgvector-kb Docker container and verify DB connectivity",
        judge_tier=1,
        max_attempts_per_hour=3,
        steps=(
            RecoveryStep(
                description="Restart pgvector-kb container",
                command="docker restart pgvector-kb",
                verify_command="docker ps --format '{{.Names}}:{{.Status}}' --filter name=pgvector-kb",
                verify_expect="pgvector-kb:Up",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_prometheus",
        component="Prometheus",
        trigger="down",
        description="Restart the Prometheus Docker container and verify readiness",
        judge_tier=1,
        max_attempts_per_hour=3,
        steps=(
            RecoveryStep(
                description="Restart prometheus container",
                command="docker restart prometheus",
                verify_command="docker ps --format '{{.Names}}:{{.Status}}' --filter name=prometheus",
                verify_expect="prometheus:Up",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_grafana",
        component="Grafana",
        trigger="down",
        description="Restart the Grafana Docker container and verify health endpoint",
        judge_tier=1,
        max_attempts_per_hour=3,
        steps=(
            RecoveryStep(
                description="Restart grafana container",
                command="docker restart grafana",
                verify_command="docker ps --format '{{.Names}}:{{.Status}}' --filter name=grafana",
                verify_expect="grafana:Up",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_pushgateway",
        component="Pushgateway",
        trigger="down",
        description="Restart the Pushgateway Docker container",
        judge_tier=1,
        max_attempts_per_hour=3,
        steps=(
            RecoveryStep(
                description="Restart pushgateway container",
                command="docker restart pushgateway",
                verify_command="docker ps --format '{{.Names}}:{{.Status}}' --filter name=pushgateway",
                verify_expect="pushgateway:Up",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_ntopng",
        component="ntopng",
        trigger="down",
        description="Restart the ntopng Docker container",
        judge_tier=1,
        max_attempts_per_hour=3,
        steps=(
            RecoveryStep(
                description="Restart ntopng container",
                command="docker restart ntopng",
                verify_command="docker ps --format '{{.Names}}:{{.Status}}' --filter name=ntopng",
                verify_expect="ntopng:Up",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_ollama",
        component="Ollama",
        trigger="down",
        description="Restart the Ollama systemd service (system-level, requires sudo)",
        judge_tier=2,
        max_attempts_per_hour=2,
        steps=(
            RecoveryStep(
                description="Restart ollama system service",
                command="sudo systemctl restart ollama",
                verify_command="systemctl is-active ollama",
                verify_expect="active",
                timeout=60,
            ),
        ),
    ),
    RecoveryPlaybook(
        name="restart_vllm",
        component="vLLM",
        trigger="down",
        description="Restart the vLLM user systemd service",
        judge_tier=1,
        max_attempts_per_hour=2,
        steps=(
            RecoveryStep(
                description="Restart vLLM user service",
                command="systemctl --user restart vllm",
                verify_command="systemctl --user is-active vllm",
                verify_expect="active",
                timeout=120,
            ),
        ),
    ),
]

# Index by (component, trigger) for fast lookup
_PLAYBOOK_INDEX: dict[tuple[str, str], RecoveryPlaybook] = {
    (p.component, p.trigger): p for p in PLAYBOOKS
}

# Canonical component names — derived from health check registry for validation
COMPONENT_NAMES: frozenset[str] = frozenset(p.component for p in PLAYBOOKS)


def get_playbook(component: str, trigger: str = "down") -> RecoveryPlaybook | None:
    """Look up a recovery playbook by component name and trigger condition.

    Returns None if no matching playbook exists.
    """
    return _PLAYBOOK_INDEX.get((component, trigger))


def get_all_playbooks() -> list[RecoveryPlaybook]:
    """Return all registered playbooks."""
    return list(PLAYBOOKS)
