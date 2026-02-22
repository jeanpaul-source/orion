"""
Unit tests for Watch Subsystem

Tests monitoring, GPU checks, alert system, and background monitoring.

Author: ORION Project
Date: November 18, 2025
"""

import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

# Alias top-level "subsystems" to the src package for compatibility with patches
sys.modules.setdefault("subsystems", importlib.import_module("src.subsystems"))

from src.subsystems.watch import (  # noqa: E402
    WatchSubsystem,
    AlertManager,
    Alert,
    AlertSeverity,
    AlertStatus,
)


@pytest.fixture
def temp_alert_file():
    """Create a temporary alert file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def alert_manager(temp_alert_file):
    """Create an AlertManager instance for testing."""
    return AlertManager(temp_alert_file)


@pytest.fixture
def watch_subsystem(temp_alert_file):
    """Create a WatchSubsystem instance for testing."""
    with patch("subsystems.watch.config") as mock_config:
        mock_config.data_dir = temp_alert_file.parent
        subsystem = WatchSubsystem.__new__(WatchSubsystem)
        subsystem.alert_manager = AlertManager(temp_alert_file)
        subsystem.thresholds = WatchSubsystem.DEFAULT_THRESHOLDS.copy()
        subsystem._monitoring_task = None
        return subsystem


class TestAlert:
    """Test Alert class."""

    def test_create_alert(self):
        """Test creating an alert."""
        alert = Alert(
            alert_id="test_alert",
            name="Test Alert",
            message="Test message",
            severity=AlertSeverity.WARNING,
            metric="cpu.percent",
            value=85.0,
            threshold=80.0,
        )

        assert alert.id == "test_alert"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.status == AlertStatus.ACTIVE
        assert alert.value == 85.0

    def test_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            alert_id="test_alert",
            name="Test Alert",
            message="Test message",
            severity=AlertSeverity.CRITICAL,
            metric="gpu.temperature",
            value=95.0,
            threshold=85.0,
        )

        data = alert.to_dict()
        assert data["severity"] == "critical"
        assert data["status"] == "active"
        assert data["value"] == 95.0

    def test_from_dict(self):
        """Test creating alert from dictionary."""
        data = {
            "id": "test_alert",
            "name": "Test Alert",
            "message": "Test message",
            "severity": "warning",
            "status": "resolved",
            "metric": "memory.percent",
            "value": 82.0,
            "threshold": 80.0,
            "created_at": "2025-11-18T00:00:00",
            "resolved_at": "2025-11-18T01:00:00",
        }

        alert = Alert.from_dict(data)
        assert alert.severity == AlertSeverity.WARNING
        assert alert.status == AlertStatus.RESOLVED


class TestAlertManager:
    """Test AlertManager class."""

    def test_create_alert(self, alert_manager):
        """Test creating an alert."""
        alert = alert_manager.create_alert(
            name="cpu_high",
            message="CPU usage is high",
            severity=AlertSeverity.WARNING,
            metric="cpu.percent",
            value=85.0,
            threshold=80.0,
        )

        assert alert.name == "cpu_high"
        assert len(alert_manager.get_active_alerts()) == 1

    def test_duplicate_alert(self, alert_manager):
        """Test that duplicate alerts update existing."""
        alert1 = alert_manager.create_alert(
            name="memory_high",
            message="Memory usage is high",
            severity=AlertSeverity.WARNING,
            metric="memory.percent",
            value=82.0,
            threshold=80.0,
        )

        # Create duplicate with different value
        alert2 = alert_manager.create_alert(
            name="memory_high",
            message="Memory usage is high",
            severity=AlertSeverity.WARNING,
            metric="memory.percent",
            value=85.0,
            threshold=80.0,
        )

        assert alert1 == alert2
        assert alert1.value == 85.0  # Value updated
        assert len(alert_manager.get_all_alerts()) == 1

    def test_resolve_alert(self, alert_manager):
        """Test resolving an alert."""
        alert_manager.create_alert(
            name="disk_high",
            message="Disk usage is high",
            severity=AlertSeverity.WARNING,
            metric="disk.percent",
            value=85.0,
            threshold=80.0,
        )

        success = alert_manager.resolve_alert("disk_high")
        assert success is True

        alert = alert_manager._alerts["disk_high"]
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None

    def test_get_active_alerts(self, alert_manager):
        """Test getting active alerts."""
        alert_manager.create_alert(
            name="alert1",
            message="Test",
            severity=AlertSeverity.WARNING,
            metric="test",
            value=1.0,
            threshold=1.0,
        )
        alert_manager.create_alert(
            name="alert2",
            message="Test",
            severity=AlertSeverity.WARNING,
            metric="test",
            value=1.0,
            threshold=1.0,
        )
        alert_manager.resolve_alert("alert1")

        active = alert_manager.get_active_alerts()
        assert len(active) == 1
        assert active[0].name == "alert2"

    def test_persistence(self, temp_alert_file):
        """Test that alerts are persisted to disk."""
        manager1 = AlertManager(temp_alert_file)
        manager1.create_alert(
            name="test_alert",
            message="Test",
            severity=AlertSeverity.INFO,
            metric="test",
            value=1.0,
            threshold=1.0,
        )

        # Create new manager instance
        manager2 = AlertManager(temp_alert_file)
        assert len(manager2.get_all_alerts()) == 1
        assert "test_alert" in manager2._alerts


class TestWatchSubsystem:
    """Test WatchSubsystem class."""

    @pytest.mark.asyncio
    async def test_check_resources(self, watch_subsystem):
        """Test resource checking."""
        resources = await watch_subsystem._check_resources()

        assert "cpu" in resources
        assert "memory" in resources
        assert "disk" in resources
        assert resources["cpu"]["percent"] >= 0
        assert resources["memory"]["total_gb"] > 0

    @pytest.mark.asyncio
    async def test_gpu_check_no_nvidia_smi(self, watch_subsystem):
        """Test GPU check when nvidia-smi not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            gpu_status = await watch_subsystem._check_gpu()

            assert gpu_status["available"] is False
            assert "nvidia-smi not found" in gpu_status["error"]

    @pytest.mark.asyncio
    async def test_gpu_check_success(self, watch_subsystem):
        """Test successful GPU check."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "0, NVIDIA GeForce RTX 3090 Ti, 45, 50, 12000, 24000, 65, 250.5\n"
        )

        with patch("subprocess.run", return_value=mock_result):
            gpu_status = await watch_subsystem._check_gpu()

            assert gpu_status["available"] is True
            assert gpu_status["name"] == "NVIDIA GeForce RTX 3090 Ti"
            assert gpu_status["utilization"] == 45.0
            assert gpu_status["temperature"] == 65.0
            assert gpu_status["memory"]["used_gb"] == pytest.approx(
                12000 / 1024, rel=1e-3
            )

    @pytest.mark.asyncio
    async def test_alert_creation_on_high_gpu_temp(self, watch_subsystem):
        """Test that alerts are created for high GPU temperature."""
        mock_result = Mock()
        mock_result.returncode = 0
        # Temperature = 90°C (above threshold of 85°C)
        mock_result.stdout = "0, RTX 3090 Ti, 50, 50, 12000, 24000, 90, 300\n"

        with patch("subprocess.run", return_value=mock_result):
            await watch_subsystem._check_gpu()

            active_alerts = watch_subsystem.alert_manager.get_active_alerts()
            alert_names = [alert.name for alert in active_alerts]
            assert "gpu_temperature_high" in alert_names

    @pytest.mark.asyncio
    async def test_alert_resolution(self, watch_subsystem):
        """Test that alerts are resolved when conditions improve."""
        # First check with high GPU temp
        mock_result_high = Mock()
        mock_result_high.returncode = 0
        mock_result_high.stdout = "0, RTX 3090 Ti, 50, 50, 12000, 24000, 90, 300\n"

        with patch("subprocess.run", return_value=mock_result_high):
            await watch_subsystem._check_gpu()

        assert len(watch_subsystem.alert_manager.get_active_alerts()) > 0

        # Second check with normal temp
        mock_result_normal = Mock()
        mock_result_normal.returncode = 0
        mock_result_normal.stdout = "0, RTX 3090 Ti, 50, 50, 12000, 24000, 70, 250\n"

        with patch("subprocess.run", return_value=mock_result_normal):
            await watch_subsystem._check_gpu()

        # Alert should be resolved
        alert = watch_subsystem.alert_manager._alerts.get("gpu_temperature_high")
        if alert:
            assert alert.status == AlertStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_get_alerts(self, watch_subsystem):
        """Test getting alerts."""
        watch_subsystem.alert_manager.create_alert(
            name="test_alert",
            message="Test",
            severity=AlertSeverity.WARNING,
            metric="test",
            value=1.0,
            threshold=1.0,
        )

        alerts = await watch_subsystem.get_alerts(active_only=True)
        assert len(alerts) == 1
        assert alerts[0]["name"] == "test_alert"

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, watch_subsystem):
        """Test acknowledging an alert."""
        watch_subsystem.alert_manager.create_alert(
            name="test_alert",
            message="Test",
            severity=AlertSeverity.INFO,
            metric="test",
            value=1.0,
            threshold=1.0,
        )

        success = await watch_subsystem.acknowledge_alert("test_alert")
        assert success is True

        alert = watch_subsystem.alert_manager._alerts["test_alert"]
        assert alert.status == AlertStatus.ACKNOWLEDGED

    def test_set_threshold(self, watch_subsystem):
        """Test setting alert threshold."""
        original = watch_subsystem.thresholds["cpu_percent"]
        watch_subsystem.set_threshold("cpu_percent", 90.0)

        assert watch_subsystem.thresholds["cpu_percent"] == 90.0
        assert watch_subsystem.thresholds["cpu_percent"] != original

    def test_determine_gpu_status(self, watch_subsystem):
        """Test GPU status determination."""
        # Healthy
        assert watch_subsystem._determine_gpu_status(50.0, 70.0, 70.0) == "healthy"

        # Warning
        assert watch_subsystem._determine_gpu_status(96.0, 70.0, 70.0) == "warning"
        assert watch_subsystem._determine_gpu_status(50.0, 91.0, 70.0) == "warning"
        assert watch_subsystem._determine_gpu_status(50.0, 70.0, 86.0) == "warning"

        # Critical
        assert watch_subsystem._determine_gpu_status(50.0, 70.0, 91.0) == "critical"
        assert watch_subsystem._determine_gpu_status(50.0, 96.0, 70.0) == "critical"

    @pytest.mark.asyncio
    async def test_anythingllm_ping_success(self, watch_subsystem):
        """Ping success should short-circuit AnythingLLM health check."""
        watch_subsystem._check_service = AsyncMock(
            return_value={"status": "healthy", "name": "AnythingLLM (RAG)"}
        )

        with patch("subsystems.watch.config") as mock_config:
            mock_config.anythingllm_url = "http://anythingllm:3001"
            result = await watch_subsystem._check_anythingllm_health()

        assert result["status"] == "healthy"
        watch_subsystem._check_service.assert_awaited_once_with(
            "http://anythingllm:3001/api/v1/system/ping",
            "AnythingLLM (RAG)",
            timeout=watch_subsystem.ANYTHINGLLM_PING_TIMEOUT,
        )

    @pytest.mark.asyncio
    async def test_anythingllm_fallback_to_auth(self, watch_subsystem):
        """Fallback to authenticated check when ping degrades."""
        watch_subsystem._check_service = AsyncMock(
            return_value={
                "status": "unhealthy",
                "name": "AnythingLLM (RAG)",
                "error": "timeout",
            }
        )
        watch_subsystem._check_service_with_auth = AsyncMock(
            return_value={
                "status": "healthy",
                "name": "AnythingLLM (RAG)",
                "latency_ms": 12.3,
            }
        )

        with patch("subsystems.watch.config") as mock_config:
            mock_config.anythingllm_url = "http://anythingllm:3001"
            mock_config.anythingllm_api_key = "test-key"  # pragma: allowlist secret
            result = await watch_subsystem._check_anythingllm_health()

        assert result["status"] == "healthy"
        watch_subsystem._check_service.assert_awaited_once_with(
            "http://anythingllm:3001/api/v1/system/ping",
            "AnythingLLM (RAG)",
            timeout=watch_subsystem.ANYTHINGLLM_PING_TIMEOUT,
        )
        watch_subsystem._check_service_with_auth.assert_awaited_once_with(
            "http://anythingllm:3001/api/v1/auth",
            "AnythingLLM (RAG)",
            "test-key",
            timeout=watch_subsystem.ANYTHINGLLM_AUTH_TIMEOUT,
        )

    @pytest.mark.asyncio
    async def test_anythingllm_missing_api_key(self, watch_subsystem):
        """Missing API key should surface configuration error."""
        watch_subsystem._check_service = AsyncMock(
            return_value={
                "status": "unhealthy",
                "name": "AnythingLLM (RAG)",
                "error": "timeout",
            }
        )

        with patch("subsystems.watch.config") as mock_config:
            mock_config.anythingllm_url = "http://anythingllm:3001"
            mock_config.anythingllm_api_key = None
            result = await watch_subsystem._check_anythingllm_health()

        assert result["status"] == "unhealthy"
        assert "missing anythingllm api key" in result["error"].lower()
        watch_subsystem._check_service.assert_awaited_once_with(
            "http://anythingllm:3001/api/v1/system/ping",
            "AnythingLLM (RAG)",
            timeout=watch_subsystem.ANYTHINGLLM_PING_TIMEOUT,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
