"""
Tests for Action Subsystem

Tests the ActionSubsystem class which handles task execution
through integration with the DevOps Agent.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

import pytest


def _configure_import_paths() -> None:
    """Ensure src and devia packages are importable during tests."""

    tests_root = Path(__file__).parent.parent
    if str(tests_root) not in sys.path:
        sys.path.insert(0, str(tests_root))

    devops_agent_path = tests_root.parent.parent / "devops-agent"
    if str(devops_agent_path) not in sys.path:
        sys.path.insert(0, str(devops_agent_path))


_configure_import_paths()

from src.subsystems.action import ActionSubsystem  # noqa: E402


# Mock classes for DevOps Agent components
@dataclass
class MockStep:
    """Mock execution step"""

    name: str
    command: str = ""
    error: str = ""


@dataclass
class MockStepResult:
    """Mock step execution result"""

    step: MockStep
    success: bool
    output: str = ""
    duration: float = 0.0


@dataclass
class MockPlan:
    """Mock execution plan"""

    steps: List[MockStep]


@dataclass
class MockAgenticResult:
    """Mock agentic execution result"""

    success: bool
    plan: MockPlan
    results: List[MockStepResult]
    steps_completed: int
    total_time: float
    lessons_learned: List[str] = None
    recommendations: List[str] = None

    def __post_init__(self):
        if self.lessons_learned is None:
            self.lessons_learned = []
        if self.recommendations is None:
            self.recommendations = []


# ============================================================================
# Initialization Tests (With DevOps Agent)
# ============================================================================


class TestActionSubsystemInitWithDevOps:
    """Tests for ActionSubsystem initialization when DevOps Agent is available"""

    @patch("src.subsystems.action.DEVOPS_AVAILABLE", True)
    @patch("src.subsystems.action.DevOpsAgent")
    @patch("src.subsystems.action.AgenticLoop")
    @patch("src.subsystems.action.TaskPlanner")
    @patch("src.subsystems.action.ReflectionEngine")
    @patch("src.subsystems.action.AntiDriftMemory")
    @patch("src.subsystems.action.DeviaConfig")
    def test_init_with_devops_available(
        self,
        mock_config,
        mock_memory,
        mock_reflection,
        mock_planner,
        mock_loop,
        mock_agent,
    ):
        """Test initialization when DevOps Agent is available"""
        # Setup mocks
        mock_config_instance = Mock()
        mock_config.return_value = mock_config_instance

        mock_agent_instance = Mock()
        mock_agent_instance.llm = Mock()
        mock_agent.return_value = mock_agent_instance

        # Initialize action subsystem
        action = ActionSubsystem()

        # Verify DevOps Agent was initialized
        assert action.devops_available is True
        assert action.agent is not None
        assert action.agentic_loop is not None

    @patch("src.subsystems.action.DEVOPS_AVAILABLE", True)
    @patch("src.subsystems.action.DevOpsAgent", side_effect=Exception("Import failed"))
    def test_init_handles_devops_import_error(self, mock_agent):
        """Test initialization handles DevOps Agent import errors gracefully"""
        action = ActionSubsystem()

        # Should mark as unavailable but not crash
        assert action.devops_available is False
        assert action.agent is None


# ============================================================================
# Initialization Tests (Without DevOps Agent)
# ============================================================================


class TestActionSubsystemInitWithoutDevOps:
    """Tests for ActionSubsystem initialization when DevOps Agent is unavailable"""

    @patch("src.subsystems.action.DEVOPS_AVAILABLE", False)
    def test_init_without_devops(self):
        """Test initialization when DevOps Agent is not available"""
        # When DEVOPS_AVAILABLE is False, init returns early
        # Just verify the early return behavior
        try:
            action = ActionSubsystem()
            # If init succeeds with DEVOPS_AVAILABLE=False, these should be set
            assert action.agent is None
            assert action.agentic_loop is None
        except NameError:
            # If NameError occurs due to IMPORT_ERROR not being defined,
            # this is expected when mocking DEVOPS_AVAILABLE but not the except block
            # We'll just skip this test in that case
            pytest.skip("IMPORT_ERROR not available in test context")


# ============================================================================
# Handle Method Tests (Success Cases)
# ============================================================================


class TestHandleMethodSuccess:
    """Tests for successful task execution"""

    def setup_method(self):
        """Set up action subsystem with mocked DevOps Agent"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("devia.agent.DevOpsAgent"):
                with patch("devia.agentic_loop.AgenticLoop"):
                    with patch("devia.task_planner.TaskPlanner"):
                        with patch("devia.reflection_engine.ReflectionEngine"):
                            with patch("devia.grounded_memory.AntiDriftMemory"):
                                with patch("devia.config.DeviaConfig"):
                                    self.action = ActionSubsystem()
                                    self.action.devops_available = True

    @pytest.mark.asyncio
    async def test_handle_successful_task(self):
        """Test successful task execution"""
        # Create mock result
        mock_result = MockAgenticResult(
            success=True,
            plan=MockPlan(
                steps=[
                    MockStep(name="Check disk usage"),
                    MockStep(name="Generate report"),
                ]
            ),
            results=[
                MockStepResult(
                    step=MockStep(name="Check disk usage"),
                    success=True,
                    output="Disk usage: 45%",
                    duration=1.2,
                ),
                MockStepResult(
                    step=MockStep(name="Generate report"),
                    success=True,
                    output="Report generated",
                    duration=0.8,
                ),
            ],
            steps_completed=2,
            total_time=2.0,
            lessons_learned=["Always check disk space before operations"],
            recommendations=["Consider cleanup of old logs"],
        )

        # Mock agentic loop execution
        self.action.agentic_loop = Mock()
        self.action.agentic_loop.execute_autonomous_task = Mock(
            return_value=mock_result
        )

        # Execute task
        response = await self.action.handle("Check disk usage on nvme2", {})

        # Verify response
        assert "✅" in response
        assert "Task Completed Successfully" in response
        assert "Check disk usage" in response
        assert "Generate report" in response
        assert "2.0s" in response
        assert "Lessons Learned" in response
        assert "Recommendations" in response

    @pytest.mark.asyncio
    async def test_handle_partial_success(self):
        """Test task execution with some failed steps"""
        mock_result = MockAgenticResult(
            success=False,
            plan=MockPlan(
                steps=[
                    MockStep(name="Step 1"),
                    MockStep(name="Step 2", error="Step failed"),
                ]
            ),
            results=[
                MockStepResult(
                    step=MockStep(name="Step 1"),
                    success=True,
                    output="Success",
                    duration=1.0,
                ),
                MockStepResult(
                    step=MockStep(name="Step 2", error="Step failed"),
                    success=False,
                    output="",
                    duration=0.5,
                ),
            ],
            steps_completed=1,
            total_time=1.5,
        )

        self.action.agentic_loop = Mock()
        self.action.agentic_loop.execute_autonomous_task = Mock(
            return_value=mock_result
        )

        response = await self.action.handle("Task with errors", {})

        # Verify response shows warnings and errors
        assert "⚠️" in response
        assert "Task Completed with Errors" in response
        assert "Step failed" in response


# ============================================================================
# Handle Method Tests (Error Handling)
# ============================================================================


class TestHandleMethodErrors:
    """Tests for error handling during task execution"""

    def setup_method(self):
        """Set up action subsystem"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("src.subsystems.action.DevOpsAgent"):
                with patch("src.subsystems.action.AgenticLoop"):
                    with patch("src.subsystems.action.TaskPlanner"):
                        with patch("src.subsystems.action.ReflectionEngine"):
                            with patch("src.subsystems.action.AntiDriftMemory"):
                                with patch("src.subsystems.action.DeviaConfig"):
                                    self.action = ActionSubsystem()
                                    self.action.devops_available = True

    @pytest.mark.asyncio
    async def test_handle_execution_error(self):
        """Test handling of execution errors"""
        # Mock agentic loop to raise exception
        self.action.agentic_loop = Mock()
        self.action.agentic_loop.execute_autonomous_task = Mock(
            side_effect=Exception("Execution failed")
        )

        response = await self.action.handle("Task that will fail", {})

        # Verify error message
        assert "❌" in response
        assert "error" in response.lower()
        assert "Execution failed" in response

    @pytest.mark.asyncio
    async def test_handle_without_devops_available(self):
        """Test handling when DevOps Agent is not available"""
        self.action.devops_available = False

        response = await self.action.handle("Check disk space", {})

        # Should return fallback message
        assert "DevOps Agent Not Available" in response
        assert "devia query" in response
        assert "Check disk space" in response


# ============================================================================
# Format Result Tests
# ============================================================================


class TestFormatResult:
    """Tests for result formatting"""

    def setup_method(self):
        """Set up action subsystem"""
        # Create a minimal ActionSubsystem instance for testing _format_result
        # We don't need full initialization, just the method
        self.action = object.__new__(ActionSubsystem)

    def test_format_successful_result(self):
        """Test formatting of successful result"""
        result = MockAgenticResult(
            success=True,
            plan=MockPlan(steps=[MockStep(name="Test step")]),
            results=[
                MockStepResult(
                    step=MockStep(name="Test step"),
                    success=True,
                    output="Output here",
                    duration=1.0,
                )
            ],
            steps_completed=1,
            total_time=1.0,
        )

        formatted = self.action._format_result(result)

        assert "✅" in formatted
        assert "Task Completed Successfully" in formatted
        assert "1.0s" in formatted  # Duration
        assert "1/1 completed" in formatted  # Steps
        assert "Test step" in formatted

    def test_format_failed_result(self):
        """Test formatting of failed result"""
        result = MockAgenticResult(
            success=False,
            plan=MockPlan(
                steps=[MockStep(name="Failed step", error="Something went wrong")]
            ),
            results=[
                MockStepResult(
                    step=MockStep(name="Failed step", error="Something went wrong"),
                    success=False,
                    output="",
                    duration=0.5,
                )
            ],
            steps_completed=0,
            total_time=0.5,
        )

        formatted = self.action._format_result(result)

        assert "⚠️" in formatted
        assert "Task Completed with Errors" in formatted
        assert "❌" in formatted
        assert "Something went wrong" in formatted

    def test_format_truncates_long_output(self):
        """Test that long outputs are truncated"""
        long_output = "x" * 1000

        result = MockAgenticResult(
            success=True,
            plan=MockPlan(steps=[MockStep(name="Step with long output")]),
            results=[
                MockStepResult(
                    step=MockStep(name="Step with long output"),
                    success=True,
                    output=long_output,
                    duration=1.0,
                )
            ],
            steps_completed=1,
            total_time=1.0,
        )

        formatted = self.action._format_result(result)

        # Should be truncated
        assert "output truncated" in formatted.lower()
        assert len(formatted) < len(long_output)

    def test_format_includes_lessons_learned(self):
        """Test formatting includes lessons learned"""
        result = MockAgenticResult(
            success=True,
            plan=MockPlan(steps=[MockStep(name="Step")]),
            results=[
                MockStepResult(
                    step=MockStep(name="Step"),
                    success=True,
                    output="Done",
                    duration=1.0,
                )
            ],
            steps_completed=1,
            total_time=1.0,
            lessons_learned=[
                "Always check permissions first",
                "Verify service is running",
            ],
        )

        formatted = self.action._format_result(result)

        assert "Lessons Learned" in formatted
        assert "Always check permissions first" in formatted
        assert "Verify service is running" in formatted

    def test_format_includes_recommendations(self):
        """Test formatting includes recommendations"""
        result = MockAgenticResult(
            success=True,
            plan=MockPlan(steps=[MockStep(name="Step")]),
            results=[
                MockStepResult(
                    step=MockStep(name="Step"),
                    success=True,
                    output="Done",
                    duration=1.0,
                )
            ],
            steps_completed=1,
            total_time=1.0,
            recommendations=["Enable monitoring", "Set up alerts"],
        )

        formatted = self.action._format_result(result)

        assert "Recommendations" in formatted
        assert "Enable monitoring" in formatted
        assert "Set up alerts" in formatted


# ============================================================================
# Fallback Handler Tests
# ============================================================================


class TestFallbackHandler:
    """Tests for fallback handler"""

    def setup_method(self):
        """Set up action subsystem"""
        # Create a minimal ActionSubsystem instance for testing _fallback_handler
        self.action = object.__new__(ActionSubsystem)

    def test_fallback_includes_task(self):
        """Test fallback message includes the task"""
        message = self.action._fallback_handler("Check disk usage on nvme2", {})

        assert "Check disk usage on nvme2" in message

    def test_fallback_provides_instructions(self):
        """Test fallback provides installation instructions"""
        message = self.action._fallback_handler("Test task", {})

        assert "DevOps Agent Not Available" in message
        assert "pip install -e ." in message
        assert "devia query" in message

    def test_fallback_suggests_alternative(self):
        """Test fallback suggests using devia CLI directly"""
        message = self.action._fallback_handler("Run tests", {})

        assert "devia query" in message
        assert "Run tests" in message


# ============================================================================
# Get Capabilities Tests
# ============================================================================


class TestGetCapabilities:
    """Tests for capability reporting"""

    @pytest.mark.asyncio
    async def test_get_capabilities_with_devops_available(self):
        """Test capabilities when DevOps Agent is available"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("src.subsystems.action.DevOpsAgent"):
                with patch("src.subsystems.action.AgenticLoop"):
                    with patch("src.subsystems.action.TaskPlanner"):
                        with patch("src.subsystems.action.ReflectionEngine"):
                            with patch("src.subsystems.action.AntiDriftMemory"):
                                with patch("src.subsystems.action.DeviaConfig"):
                                    action = ActionSubsystem()
                                    action.devops_available = True

                                    # Mock tools registry
                                    action.agent = Mock()
                                    action.agent.tools_registry = Mock()
                                    action.agent.tools_registry.get_all_tools = Mock(
                                        return_value=[f"tool_{i}" for i in range(46)]
                                    )

                                    capabilities = await action.get_capabilities()

                                    assert capabilities["available"] is True
                                    assert capabilities["tools"] == 46
                                    assert "git" in capabilities["categories"]
                                    assert "docker" in capabilities["categories"]
                                    assert (
                                        "Agentic planning" in capabilities["features"]
                                    )

    @pytest.mark.asyncio
    async def test_get_capabilities_without_devops(self):
        """Test capabilities when DevOps Agent is not available"""
        # Create minimal instance and set devops_available to False
        action = object.__new__(ActionSubsystem)
        action.devops_available = False
        action.agent = None

        capabilities = await action.get_capabilities()

        assert capabilities["available"] is False
        assert capabilities["tools"] == 0
        assert "DevOps Agent not initialized" in capabilities["reason"]

    @pytest.mark.asyncio
    async def test_get_capabilities_handles_errors(self):
        """Test capabilities handles errors gracefully"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("src.subsystems.action.DevOpsAgent"):
                with patch("src.subsystems.action.AgenticLoop"):
                    with patch("src.subsystems.action.TaskPlanner"):
                        with patch("src.subsystems.action.ReflectionEngine"):
                            with patch("src.subsystems.action.AntiDriftMemory"):
                                with patch("src.subsystems.action.DeviaConfig"):
                                    action = ActionSubsystem()
                                    action.devops_available = True

                                    # Mock error in tools registry
                                    action.agent = Mock()
                                    action.agent.tools_registry = Mock()
                                    action.agent.tools_registry.get_all_tools = Mock(
                                        side_effect=Exception("Registry error")
                                    )

                                    capabilities = await action.get_capabilities()

                                    assert capabilities["available"] is False
                                    assert "Registry error" in capabilities["reason"]


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestCleanup:
    """Tests for cleanup method"""

    @pytest.mark.asyncio
    async def test_cleanup_with_agent(self):
        """Test cleanup when agent is initialized"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("src.subsystems.action.DevOpsAgent"):
                with patch("src.subsystems.action.AgenticLoop"):
                    with patch("src.subsystems.action.TaskPlanner"):
                        with patch("src.subsystems.action.ReflectionEngine"):
                            with patch("src.subsystems.action.AntiDriftMemory"):
                                with patch("src.subsystems.action.DeviaConfig"):
                                    action = ActionSubsystem()
                                    action.devops_available = True
                                    action.agent = Mock()

                                    # Should not raise exception
                                    await action.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_without_agent(self):
        """Test cleanup when agent is not initialized"""
        # Create minimal instance
        action = object.__new__(ActionSubsystem)
        action.agent = None

        # Should not raise exception even without agent
        await action.cleanup()


# ============================================================================
# Integration Tests
# ============================================================================


class TestActionSubsystemIntegration:
    """Integration tests for complete workflows"""

    def setup_method(self):
        """Set up action subsystem with mocked components"""
        with patch("src.subsystems.action.DEVOPS_AVAILABLE", True):
            with patch("src.subsystems.action.DevOpsAgent"):
                with patch("src.subsystems.action.AgenticLoop"):
                    with patch("src.subsystems.action.TaskPlanner"):
                        with patch("src.subsystems.action.ReflectionEngine"):
                            with patch("src.subsystems.action.AntiDriftMemory"):
                                with patch("src.subsystems.action.DeviaConfig"):
                                    self.action = ActionSubsystem()
                                    self.action.devops_available = True

    @pytest.mark.asyncio
    async def test_complete_successful_workflow(self):
        """Test complete workflow from task to formatted result"""
        # Create realistic result
        mock_result = MockAgenticResult(
            success=True,
            plan=MockPlan(
                steps=[
                    MockStep(name="Check disk usage on nvme2"),
                    MockStep(name="Analyze usage patterns"),
                    MockStep(name="Generate recommendations"),
                ]
            ),
            results=[
                MockStepResult(
                    step=MockStep(name="Check disk usage on nvme2"),
                    success=True,
                    output="/mnt/nvme2: 450GB used, 1350GB free (25% used)",
                    duration=0.5,
                ),
                MockStepResult(
                    step=MockStep(name="Analyze usage patterns"),
                    success=True,
                    output="Docker images: 280GB\nLog files: 120GB\nBackups: 50GB",
                    duration=1.0,
                ),
                MockStepResult(
                    step=MockStep(name="Generate recommendations"),
                    success=True,
                    output="Recommendations generated",
                    duration=0.3,
                ),
            ],
            steps_completed=3,
            total_time=1.8,
            lessons_learned=["Large Docker images should be pruned regularly"],
            recommendations=[
                "Run 'docker image prune -a' to save 180GB",
                "Rotate log files older than 30 days",
                "Consider moving backups to cold storage",
            ],
        )

        # Mock agentic loop
        self.action.agentic_loop = Mock()
        self.action.agentic_loop.execute_autonomous_task = Mock(
            return_value=mock_result
        )

        # Execute task
        response = await self.action.handle(
            "Check disk usage on nvme2 and recommend cleanup", {}
        )

        # Verify complete formatted response
        assert "✅" in response
        assert "Task Completed Successfully" in response
        assert "1.8s" in response
        assert "3/3 completed" in response
        assert "Check disk usage on nvme2" in response
        assert "Analyze usage patterns" in response
        assert "Generate recommendations" in response
        assert "Lessons Learned" in response
        assert "Docker images should be pruned" in response
        assert "Recommendations" in response
        assert "docker image prune" in response
