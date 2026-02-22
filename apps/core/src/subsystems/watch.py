"""
Watch Subsystem

Handles system monitoring, health checks, and alerting.
Monitors all services and provides status reports with proactive alerts.

Features:
- Service health monitoring (vLLM, Qdrant, AnythingLLM)
- Resource monitoring (CPU, RAM, Disk, GPU)
- Alert system with configurable thresholds
- Alert history and state tracking
- Background monitoring task

Author: ORION Project
Date: November 18, 2025
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import psutil

from ..config import config

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class Alert:
    """
    A single alert/warning.

    Attributes:
        id: Unique alert ID
        name: Alert name
        message: Alert message
        severity: Alert severity (info, warning, critical)
        status: Alert status (active, resolved, acknowledged)
        metric: Related metric name
        value: Current metric value
        threshold: Threshold that triggered alert
        created_at: When alert was created
        resolved_at: When alert was resolved (if applicable)
    """

    def __init__(
        self,
        alert_id: str,
        name: str,
        message: str,
        severity: AlertSeverity,
        metric: str,
        value: float,
        threshold: float,
        status: AlertStatus = AlertStatus.ACTIVE,
        created_at: Optional[str] = None,
        resolved_at: Optional[str] = None,
    ):
        self.id = alert_id
        self.name = name
        self.message = message
        self.severity = severity
        self.status = status
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.resolved_at = resolved_at

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "message": self.message,
            "severity": self.severity.value,
            "status": self.status.value,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Alert":
        """Create from dictionary."""
        return cls(
            alert_id=data["id"],
            name=data["name"],
            message=data["message"],
            severity=AlertSeverity(data["severity"]),
            metric=data["metric"],
            value=data["value"],
            threshold=data["threshold"],
            status=AlertStatus(data.get("status", "active")),
            created_at=data.get("created_at"),
            resolved_at=data.get("resolved_at"),
        )


class AlertManager:
    """
    Manages alert state, history, and persistence.
    """

    def __init__(self, alert_file: Path):
        self.alert_file = alert_file
        self.alert_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing alerts
        self._alerts: Dict[str, Alert] = self._load()

    def _load(self) -> Dict[str, Alert]:
        """Load alerts from disk."""
        if not self.alert_file.exists():
            logger.info(f"Alert file not found, creating new: {self.alert_file}")
            return {}

        try:
            with open(self.alert_file, "r") as f:
                data = json.load(f)
                return {
                    alert_id: Alert.from_dict(alert_data)
                    for alert_id, alert_data in data.items()
                }
        except Exception as e:
            logger.error(f"Failed to load alerts: {e}")
            return {}

    def _save(self):
        """Save alerts to disk."""
        try:
            with open(self.alert_file, "w") as f:
                data = {
                    alert_id: alert.to_dict()
                    for alert_id, alert in self._alerts.items()
                }
                json.dump(data, f, indent=2)
            logger.debug(f"Saved alerts ({len(self._alerts)} total)")
        except Exception as e:
            logger.error(f"Failed to save alerts: {e}")

    def create_alert(
        self,
        name: str,
        message: str,
        severity: AlertSeverity,
        metric: str,
        value: float,
        threshold: float,
    ) -> Alert:
        """
        Create a new alert.

        Args:
            name: Alert name (used as ID for deduplication)
            message: Alert message
            severity: Alert severity
            metric: Related metric
            value: Current value
            threshold: Threshold that triggered

        Returns:
            Created or existing alert
        """
        # Check if alert already exists (by name)
        if name in self._alerts:
            existing = self._alerts[name]
            # Update value if still active
            if existing.status == AlertStatus.ACTIVE:
                existing.value = value
                self._save()
                return existing

        # Create new alert
        alert = Alert(
            alert_id=name,
            name=name,
            message=message,
            severity=severity,
            metric=metric,
            value=value,
            threshold=threshold,
        )

        self._alerts[name] = alert
        self._save()

        logger.warning(f"Alert created: {name} - {message}")
        return alert

    def resolve_alert(self, name: str) -> bool:
        """
        Resolve an alert by name.

        Args:
            name: Alert name/ID

        Returns:
            True if alert was found and resolved
        """
        if name not in self._alerts:
            return False

        alert = self._alerts[name]
        if alert.status == AlertStatus.ACTIVE:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(timezone.utc).isoformat()
            self._save()
            logger.info(f"Alert resolved: {name}")
            return True

        return False

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return [
            alert
            for alert in self._alerts.values()
            if alert.status == AlertStatus.ACTIVE
        ]

    def get_all_alerts(self, limit: int = 50) -> List[Alert]:
        """Get all alerts (most recent first)."""
        alerts = sorted(self._alerts.values(), key=lambda x: x.created_at, reverse=True)
        return alerts[:limit]

    def cleanup_old_resolved(self, days: int = 7):
        """
        Remove resolved alerts older than specified days.

        Args:
            days: Number of days to keep resolved alerts
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        to_remove = []

        for alert_id, alert in self._alerts.items():
            if alert.status == AlertStatus.RESOLVED and alert.resolved_at:
                resolved_time = datetime.fromisoformat(alert.resolved_at)
                if resolved_time < cutoff:
                    to_remove.append(alert_id)

        for alert_id in to_remove:
            del self._alerts[alert_id]

        if to_remove:
            self._save()
            logger.info(f"Cleaned up {len(to_remove)} old resolved alerts")


class WatchSubsystem:
    """
    Watch subsystem for monitoring and health checks.

    Monitors:
    - Service health (vLLM, Qdrant, AnythingLLM)
    - System resources (CPU, RAM, disk, GPU)
    - Container status
    - Network connectivity

    Features:
    - Configurable alert thresholds
    - Alert history and state tracking
    - Background monitoring task (optional)
    - Proactive notifications
    """

    # Default alert thresholds
    DEFAULT_THRESHOLDS = {
        "cpu_percent": 80.0,
        "memory_percent": 80.0,
        "disk_percent": 80.0,
        "gpu_utilization": 95.0,
        "gpu_memory_percent": 90.0,
        "gpu_temperature": 85.0,
    }

    ANYTHINGLLM_PING_TIMEOUT = 20.0
    ANYTHINGLLM_AUTH_TIMEOUT = 25.0

    def __init__(self, enable_background_monitoring: bool = False):
        # Initialize alert manager
        alert_file = config.data_dir / "alerts.json"
        self.alert_manager = AlertManager(alert_file)

        # Alert thresholds (can be overridden)
        self.thresholds = self.DEFAULT_THRESHOLDS.copy()

        # Background monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        if enable_background_monitoring:
            self._monitoring_task = asyncio.create_task(self._background_monitoring())

        logger.info(
            f"Watch subsystem initialized "
            f"(background monitoring: {enable_background_monitoring}, "
            f"{len(self.alert_manager.get_active_alerts())} active alerts)"
        )

    async def handle(self, query: str, context: Dict) -> str:
        """
        Handle monitoring query.

        Args:
            query: What to monitor/check
            context: Conversation context

        Returns:
            Status report

        Example:
            >>> watch = WatchSubsystem()
            >>> status = await watch.handle(
            ...     "check system health",
            ...     context={}
            ... )
        """
        logger.info(f"Watch query: {query}")

        try:
            # Get comprehensive system status
            report = await self.get_full_status()
            return self._format_status_report(report)

        except Exception as e:
            logger.exception("Watch subsystem error")
            return f"I encountered an error checking system status: {str(e)}"

    async def get_full_status(self) -> Dict:
        """
        Get comprehensive system status.

        Returns:
            Dict with all system health information
        """
        status = {
            "timestamp": datetime.now().isoformat(),
            "services": await self._check_services(),
            "resources": await self._check_resources(),
            "gpu": await self._check_gpu(),
            "alerts": {
                "active": len(self.alert_manager.get_active_alerts()),
                "total": len(self.alert_manager.get_all_alerts(limit=100)),
            },
            "overall": "healthy",  # Will be updated based on checks
        }

        # Determine overall health
        unhealthy_services = [
            name
            for name, info in status["services"].items()
            if info.get("status") != "healthy"
        ]

        active_critical_alerts = [
            alert
            for alert in self.alert_manager.get_active_alerts()
            if alert.severity == AlertSeverity.CRITICAL
        ]

        if unhealthy_services or active_critical_alerts:
            status["overall"] = "critical"
            status["issues"] = unhealthy_services
        elif len(self.alert_manager.get_active_alerts()) > 0:
            status["overall"] = "degraded"

        return status

    async def _check_services(self) -> Dict:
        """
        Check health of all ORION services.

        Returns:
            Dict of service statuses
        """
        services = {}

        # Check vLLM
        services["vllm"] = await self._check_service(
            f"{config.vllm_url}/health", "vLLM (LLM Inference)"
        )

        # Check Qdrant
        services["qdrant"] = await self._check_service(
            f"{config.qdrant_url}/", "Qdrant (Vector DB)"
        )

        # Get Qdrant collection stats if service is healthy
        if services["qdrant"]["status"] == "healthy":
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(
                        f"{config.qdrant_url}/collections/{config.qdrant_collection}"
                    )
                    if response.status_code == 200:
                        data = response.json()
                        vector_count = data.get("result", {}).get(
                            "vectors_count"
                        ) or data.get("result", {}).get("points_count", 0)
                        services["qdrant"]["vectors"] = vector_count
                        services["qdrant"]["rebuild_required"] = vector_count <= 0
                    elif response.status_code == 404:
                        # Collection doesn't exist yet - show 0 vectors
                        services["qdrant"]["vectors"] = 0
                        services["qdrant"]["rebuild_required"] = True
            except Exception as e:
                logger.warning(f"Could not get Qdrant collection stats: {e}")
                services["qdrant"]["rebuild_required"] = True

        # Check AnythingLLM using fast ping + authenticated fallback
        services["anythingllm"] = await self._check_anythingllm_health()

        # Check for unhealthy services and create alerts
        for service_name, service_info in services.items():
            if service_info["status"] == "unhealthy":
                self.alert_manager.create_alert(
                    name=f"service_{service_name}_down",
                    message=f"{service_info['name']} is unreachable",
                    severity=AlertSeverity.CRITICAL,
                    metric=f"service.{service_name}.health",
                    value=0,
                    threshold=1,
                )
            else:
                # Resolve alert if service is back up
                self.alert_manager.resolve_alert(f"service_{service_name}_down")

        return services

    async def _check_service(
        self, url: str, name: str, *, timeout: float = 5.0
    ) -> Dict:
        """
        Check individual service health.

        Args:
            url: Service health endpoint
            name: Service display name

        Returns:
            Service status dict
        """
        try:
            client_timeout = httpx.Timeout(
                timeout,
                connect=min(timeout, 5.0),
                read=timeout,
            )
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                start_time = datetime.now()
                response = await client.get(url)
                latency_ms = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "name": name,
                        "latency_ms": round(latency_ms, 2),
                    }
                else:
                    return {
                        "status": "degraded",
                        "name": name,
                        "error": f"HTTP {response.status_code}",
                    }

        except Exception as e:
            logger.warning(f"Service check failed for {name}: {e}")
            return {"status": "unhealthy", "name": name, "error": str(e)}

    async def _check_anythingllm_health(self) -> Dict:
        """Check AnythingLLM health with ping + authenticated fallback."""
        service_name = "AnythingLLM (RAG)"
        ping_url = f"{config.anythingllm_url}/api/v1/system/ping"

        primary_result = await self._check_service(
            ping_url,
            service_name,
            timeout=self.ANYTHINGLLM_PING_TIMEOUT,
        )

        if primary_result.get("status") == "healthy":
            return primary_result

        api_key = config.anythingllm_api_key

        if not api_key:
            error_msg = primary_result.get("error") or "Missing ping response"
            logger.warning(
                "AnythingLLM ping check failed (%s) and no API key is configured for fallback",
                error_msg,
            )
            return {
                **primary_result,
                "error": f"{error_msg} (missing AnythingLLM API key)",
            }

        logger.info(
            "AnythingLLM ping degraded (%s). Retrying with authenticated endpoint.",
            primary_result.get("error", "unknown error"),
        )

        fallback_result = await self._check_service_with_auth(
            f"{config.anythingllm_url}/api/v1/auth",
            service_name,
            api_key,
            timeout=self.ANYTHINGLLM_AUTH_TIMEOUT,
        )

        if fallback_result.get("status") == "healthy":
            return fallback_result

        if not fallback_result.get("error") and primary_result.get("error"):
            fallback_result["error"] = primary_result["error"]

        return fallback_result

    async def _check_service_with_auth(
        self, url: str, name: str, api_key: Optional[str], timeout: float = 5.0
    ) -> Dict:
        """
        Check individual service health with Bearer token authentication.

        Args:
            url: Service health endpoint
            name: Service display name
            api_key: Bearer token for authentication
            timeout: Request timeout in seconds

        Returns:
            Service status dict
        """
        if not api_key:
            logger.warning("Skipping authenticated check for %s: missing API key", name)
            return {
                "status": "unhealthy",
                "name": name,
                "error": "Missing API key",
            }

        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            client_timeout = httpx.Timeout(
                timeout,
                connect=min(timeout, 5.0),
                read=timeout,
            )
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                start_time = datetime.now()
                response = await client.get(url, headers=headers)
                latency_ms = (datetime.now() - start_time).total_seconds() * 1000

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "name": name,
                        "latency_ms": round(latency_ms, 2),
                    }
                else:
                    body_preview = response.text.strip()[:120]
                    error = f"HTTP {response.status_code}"
                    if body_preview:
                        error = f"{error}: {body_preview}"
                    return {
                        "status": "degraded",
                        "name": name,
                        "error": error,
                    }

        except Exception as e:
            logger.warning("Service check failed for %s: %s", name, e)
            return {"status": "unhealthy", "name": name, "error": str(e)}

    async def _check_resources(self) -> Dict:
        """
        Check system resource usage.

        Returns:
            Resource usage dict
        """
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory
            memory = psutil.virtual_memory()

            # Disk (check configured data directory)
            disk_path = str(config.data_dir)
            disk = psutil.disk_usage(disk_path)

            # Check thresholds and create alerts
            if cpu_percent > self.thresholds["cpu_percent"]:
                self.alert_manager.create_alert(
                    name="cpu_high",
                    message=f"CPU usage is {cpu_percent:.1f}% (threshold: {self.thresholds['cpu_percent']}%)",
                    severity=AlertSeverity.WARNING,
                    metric="cpu.percent",
                    value=cpu_percent,
                    threshold=self.thresholds["cpu_percent"],
                )
            else:
                self.alert_manager.resolve_alert("cpu_high")

            if memory.percent > self.thresholds["memory_percent"]:
                self.alert_manager.create_alert(
                    name="memory_high",
                    message=f"Memory usage is {memory.percent:.1f}% (threshold: {self.thresholds['memory_percent']}%)",
                    severity=AlertSeverity.WARNING,
                    metric="memory.percent",
                    value=memory.percent,
                    threshold=self.thresholds["memory_percent"],
                )
            else:
                self.alert_manager.resolve_alert("memory_high")

            if disk.percent > self.thresholds["disk_percent"]:
                self.alert_manager.create_alert(
                    name="disk_high",
                    message=f"Disk usage is {disk.percent:.1f}% (threshold: {self.thresholds['disk_percent']}%)",
                    severity=(
                        AlertSeverity.CRITICAL
                        if disk.percent > 90
                        else AlertSeverity.WARNING
                    ),
                    metric="disk.percent",
                    value=disk.percent,
                    threshold=self.thresholds["disk_percent"],
                )
            else:
                self.alert_manager.resolve_alert("disk_high")

            return {
                "cpu": {
                    "percent": round(cpu_percent, 1),
                    "status": (
                        "healthy"
                        if cpu_percent < self.thresholds["cpu_percent"]
                        else "warning"
                    ),
                },
                "memory": {
                    "percent": round(memory.percent, 1),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "total_gb": round(memory.total / (1024**3), 2),
                    "status": (
                        "healthy"
                        if memory.percent < self.thresholds["memory_percent"]
                        else "warning"
                    ),
                },
                "disk": {
                    "percent": round(disk.percent, 1),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "total_gb": round(disk.total / (1024**3), 2),
                    "status": (
                        "healthy"
                        if disk.percent < self.thresholds["disk_percent"]
                        else "warning"
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Resource check failed: {e}")
            return {"error": str(e)}

    async def _check_gpu(self) -> Dict:
        """
        Check GPU status using nvidia-smi.

        Returns:
            GPU status dict
        """
        try:
            # Run nvidia-smi to get GPU info
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.warning(f"nvidia-smi failed: {result.stderr}")
                return {"available": False, "error": "nvidia-smi command failed"}

            # Parse output
            lines = result.stdout.strip().split("\n")
            if not lines or not lines[0]:
                return {"available": False, "error": "No GPU detected"}

            # Parse first GPU (we have 1x RTX 3090 Ti)
            parts = [p.strip() for p in lines[0].split(",")]
            if len(parts) < 8:
                return {
                    "available": False,
                    "error": "Unexpected nvidia-smi output format",
                }

            (
                gpu_index,
                gpu_name,
                util_gpu,
                util_mem,
                mem_used,
                mem_total,
                temp,
                power,
            ) = parts

            # Convert to proper types
            utilization = float(util_gpu)
            memory_utilization = float(util_mem)
            memory_used_mb = float(mem_used)
            memory_total_mb = float(mem_total)
            temperature = float(temp)
            power_draw = float(power) if power != "[N/A]" else 0.0

            memory_percent = (memory_used_mb / memory_total_mb) * 100

            # Check thresholds and create alerts
            if utilization > self.thresholds["gpu_utilization"]:
                self.alert_manager.create_alert(
                    name="gpu_utilization_high",
                    message=f"GPU utilization is {utilization:.1f}% (threshold: {self.thresholds['gpu_utilization']}%)",
                    severity=AlertSeverity.WARNING,
                    metric="gpu.utilization",
                    value=utilization,
                    threshold=self.thresholds["gpu_utilization"],
                )
            else:
                self.alert_manager.resolve_alert("gpu_utilization_high")

            if memory_percent > self.thresholds["gpu_memory_percent"]:
                self.alert_manager.create_alert(
                    name="gpu_memory_high",
                    message=f"GPU memory is {memory_percent:.1f}% (threshold: {self.thresholds['gpu_memory_percent']}%)",
                    severity=AlertSeverity.WARNING,
                    metric="gpu.memory.percent",
                    value=memory_percent,
                    threshold=self.thresholds["gpu_memory_percent"],
                )
            else:
                self.alert_manager.resolve_alert("gpu_memory_high")

            if temperature > self.thresholds["gpu_temperature"]:
                self.alert_manager.create_alert(
                    name="gpu_temperature_high",
                    message=f"GPU temperature is {temperature:.0f}°C (threshold: {self.thresholds['gpu_temperature']}°C)",
                    severity=(
                        AlertSeverity.CRITICAL
                        if temperature > 90
                        else AlertSeverity.WARNING
                    ),
                    metric="gpu.temperature",
                    value=temperature,
                    threshold=self.thresholds["gpu_temperature"],
                )
            else:
                self.alert_manager.resolve_alert("gpu_temperature_high")

            return {
                "available": True,
                "name": gpu_name,
                "index": int(gpu_index),
                "utilization": round(utilization, 1),
                "memory": {
                    "utilization": round(memory_utilization, 1),
                    "used_mb": round(memory_used_mb, 0),
                    "total_mb": round(memory_total_mb, 0),
                    "used_gb": round(memory_used_mb / 1024, 2),
                    "total_gb": round(memory_total_mb / 1024, 2),
                    "percent": round(memory_percent, 1),
                },
                "temperature": round(temperature, 1),
                "power_draw": round(power_draw, 1),
                "status": self._determine_gpu_status(
                    utilization, memory_percent, temperature
                ),
            }

        except FileNotFoundError:
            logger.debug("nvidia-smi not found (no GPU or drivers not installed)")
            return {"available": False, "error": "nvidia-smi not found"}
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timeout")
            return {"available": False, "error": "nvidia-smi timeout"}
        except Exception as e:
            logger.error(f"GPU check failed: {e}")
            return {"available": False, "error": str(e)}

    def _determine_gpu_status(
        self, utilization: float, memory_percent: float, temperature: float
    ) -> str:
        """Determine overall GPU status."""
        if temperature > 90 or memory_percent > 95:
            return "critical"
        elif (
            temperature > self.thresholds["gpu_temperature"]
            or memory_percent > self.thresholds["gpu_memory_percent"]
            or utilization > self.thresholds["gpu_utilization"]
        ):
            return "warning"
        else:
            return "healthy"

    def _format_status_report(self, status: Dict) -> str:
        """
        Format status dict into user-friendly report.

        Args:
            status: Status dict from get_full_status()

        Returns:
            Formatted status report
        """
        overall = status["overall"]
        emoji_map = {"healthy": "🟢", "degraded": "🟡", "critical": "🔴"}
        emoji = emoji_map.get(overall, "⚪")

        report = f"{emoji} **ORION System Status**\n"
        report += f"*As of {status['timestamp']}*\n\n"

        # Overall
        report += f"**Overall:** {overall.upper()}\n\n"

        # Services
        report += "**Services:**\n"
        for service_info in status["services"].values():
            status_emoji = {
                "healthy": "🟢",
                "degraded": "🟡",
                "unhealthy": "🔴",
            }.get(service_info["status"], "⚪")

            latency = (
                f" ({service_info['latency_ms']}ms)"
                if service_info.get("latency_ms")
                else ""
            )
            report += f"{status_emoji} {service_info['name']}: {service_info['status']}{latency}\n"

        # Resources
        if "resources" in status and "error" not in status["resources"]:
            res = status["resources"]
            report += "\n**Resources:**\n"

            if "cpu" in res:
                emoji = "🟢" if res["cpu"]["status"] == "healthy" else "🟡"
                report += f"{emoji} CPU: {res['cpu']['percent']}%\n"

            if "memory" in res:
                mem = res["memory"]
                emoji = "🟢" if mem["status"] == "healthy" else "🟡"
                report += f"{emoji} Memory: {mem['used_gb']}GB / {mem['total_gb']}GB ({mem['percent']}%)\n"

            if "disk" in res:
                disk = res["disk"]
                emoji = "🟢" if disk["status"] == "healthy" else "🟡"
                report += f"{emoji} Disk: {disk['used_gb']}GB / {disk['total_gb']}GB ({disk['percent']}%)\n"

        # GPU
        if "gpu" in status:
            gpu = status["gpu"]
            if gpu.get("available"):
                report += "\n**GPU:**\n"
                emoji_map = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}
                emoji = emoji_map.get(gpu.get("status", "healthy"), "⚪")

                report += f"{emoji} {gpu['name']}\n"
                report += f"  • Utilization: {gpu['utilization']}%\n"
                report += f"  • VRAM: {gpu['memory']['used_gb']}GB / {gpu['memory']['total_gb']}GB ({gpu['memory']['percent']}%)\n"
                report += f"  • Temperature: {gpu['temperature']}°C\n"
                if gpu.get("power_draw", 0) > 0:
                    report += f"  • Power: {gpu['power_draw']}W\n"

        # Active Alerts
        active_alerts = self.alert_manager.get_active_alerts()
        if active_alerts:
            report += f"\n**🚨 Active Alerts ({len(active_alerts)}):**\n"
            for alert in active_alerts[:5]:  # Show first 5
                severity_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}.get(
                    alert.severity.value, "⚪"
                )
                report += f"{severity_emoji} {alert.message}\n"

            if len(active_alerts) > 5:
                report += f"... and {len(active_alerts) - 5} more alerts\n"

        return report

    async def get_alerts(self, active_only: bool = True, limit: int = 50) -> List[Dict]:
        """
        Get alerts.

        Args:
            active_only: Only return active alerts
            limit: Maximum number of alerts to return

        Returns:
            List of alert dicts
        """
        if active_only:
            alerts = self.alert_manager.get_active_alerts()
        else:
            alerts = self.alert_manager.get_all_alerts(limit=limit)

        return [alert.to_dict() for alert in alerts]

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID to acknowledge

        Returns:
            True if successful
        """
        if alert_id in self.alert_manager._alerts:
            alert = self.alert_manager._alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            self.alert_manager._save()
            logger.info(f"Alert acknowledged: {alert_id}")
            return True
        return False

    def set_threshold(self, metric: str, value: float):
        """
        Update an alert threshold.

        Args:
            metric: Metric name (e.g., "cpu_percent")
            value: New threshold value
        """
        if metric in self.thresholds:
            old_value = self.thresholds[metric]
            self.thresholds[metric] = value
            logger.info(f"Threshold updated: {metric} {old_value} → {value}")
        else:
            logger.warning(f"Unknown threshold metric: {metric}")

    async def _background_monitoring(self):
        """
        Background task that runs health checks periodically.

        Runs every 60 seconds and checks all systems.
        """
        logger.info("Background monitoring started")

        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Run health checks
                status = await self.get_full_status()

                # Log overall status
                logger.info(
                    f"Health check: {status['overall']} "
                    f"({len(self.alert_manager.get_active_alerts())} active alerts)"
                )

                # Cleanup old resolved alerts (weekly)
                if datetime.now().hour == 3:  # 3am cleanup
                    self.alert_manager.cleanup_old_resolved(days=7)

            except asyncio.CancelledError:
                logger.info("Background monitoring stopped")
                break
            except Exception:
                logger.exception("Background monitoring error")

    async def stop_background_monitoring(self):
        """Stop the background monitoring task."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("Background monitoring stopped")
