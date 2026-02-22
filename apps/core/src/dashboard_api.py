"""
Dashboard API Endpoints
Provides data for the ORION dashboard UI
"""

import logging
import psutil
import time
from typing import Dict, Any, Optional
from fastapi import Request, Header

logger = logging.getLogger(__name__)

# Track application start time
APP_START_TIME = time.time()


def get_uptime() -> str:
    """Get application uptime in human-readable format."""
    uptime_seconds = time.time() - APP_START_TIME
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


async def get_user_info(
    request: Request,
    remote_user: Optional[str] = Header(None, alias="Remote-User"),
    remote_name: Optional[str] = Header(None, alias="Remote-Name"),
    remote_email: Optional[str] = Header(None, alias="Remote-Email"),
    remote_groups: Optional[str] = Header(None, alias="Remote-Groups"),
) -> Dict[str, Any]:
    """
    Get user information from Authelia headers (set by Traefik).

    Headers set by Authelia forward auth:
    - Remote-User: username
    - Remote-Name: display name
    - Remote-Email: email address
    - Remote-Groups: comma-separated groups
    """
    if remote_user:
        return {
            "username": remote_user,
            "displayName": remote_name or remote_user,
            "email": remote_email,
            "groups": remote_groups.split(",") if remote_groups else [],
            "authenticated": True,
        }
    else:
        # No auth headers - user is on public route
        return {
            "username": "guest",
            "displayName": "Guest",
            "email": None,
            "groups": [],
            "authenticated": False,
        }


async def get_dashboard_status(request: Request) -> Dict[str, Any]:
    """
    Get comprehensive dashboard status.

    Returns service health, resource metrics, and system information.
    """
    try:
        # Get router (for watch subsystem)
        router = request.app.state.router

        # Try to get status from watch subsystem
        try:
            full_status = await router.watch.get_full_status()
            services = full_status.get("services", {})
        except Exception as e:
            logger.warning(f"Could not get watch status: {e}")
            services = {}

        # Build service status (with fallbacks)
        service_status = {
            "orion_core": {
                "status": "healthy",
                "uptime": get_uptime(),
                "requests": getattr(request.app.state, "request_count", 0),
            },
            "vllm": services.get(
                "vllm",
                {
                    "status": "unknown",
                    "gpu_temp": None,
                },
            ),
            "qdrant": services.get(
                "qdrant",
                {
                    "status": "unknown",
                    "collections": None,
                    "vectors": None,
                },
            ),
            "authelia": services.get(
                "authelia",
                {
                    "status": "unknown",
                    "sessions": None,
                },
            ),
        }

        # Get resource usage
        resources = get_resource_usage()

        return {
            "services": service_status,
            "resources": resources,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.exception("Error getting dashboard status")
        return {
            "services": {
                "orion_core": {
                    "status": "degraded",
                    "uptime": get_uptime(),
                    "requests": 0,
                },
            },
            "resources": get_resource_usage(),
            "timestamp": time.time(),
            "error": str(e),
        }


def get_resource_usage() -> Dict[str, Any]:
    """
    Get system resource usage (CPU, memory, disk).

    For GPU usage, requires nvidia-smi or similar tool.
    """
    resources = {}

    # Memory usage
    try:
        memory = psutil.virtual_memory()
        resources["memory"] = {
            "total": memory.total,
            "used": memory.used,
            "percent": memory.percent,
        }
    except Exception as e:
        logger.warning(f"Could not get memory usage: {e}")
        resources["memory"] = {"total": 0, "used": 0, "percent": 0}

    # Disk usage - aggregate all NVMe drives
    # When running in Docker, host filesystems are mounted as /host-*
    try:
        # Detect if running in container (host mounts available)
        import os

        if os.path.exists("/host-root"):
            # Running in container with host mounts
            drives = [
                ("/host-root", "/"),
                ("/host-nvme1", "/mnt/nvme1"),
                ("/host-nvme2", "/mnt/nvme2"),
            ]
        else:
            # Running directly on host or laptop
            drives = [
                ("/", "/"),
                ("/mnt/nvme1", "/mnt/nvme1"),
                ("/mnt/nvme2", "/mnt/nvme2"),
            ]

        total_bytes = 0
        used_bytes = 0
        drive_details = []

        for actual_path, display_path in drives:
            try:
                disk = psutil.disk_usage(actual_path)
                total_bytes += disk.total
                used_bytes += disk.used
                drive_details.append(
                    {
                        "path": display_path,  # Show original path to user
                        "total": disk.total,
                        "used": disk.used,
                        "percent": disk.percent,
                    }
                )
            except Exception as e:
                logger.debug(f"Could not get disk usage for {display_path}: {e}")
                continue

        # Calculate aggregate percentage
        percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0

        resources["disk"] = {
            "total": total_bytes,
            "used": used_bytes,
            "percent": percent,
            "drives": drive_details,  # Individual drive breakdowns
        }
    except Exception as e:
        logger.warning(f"Could not get disk usage: {e}")
        resources["disk"] = {"total": 0, "used": 0, "percent": 0, "drives": []}

    # GPU usage (if available)
    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            total_mb = float(parts[0].strip())
            used_mb = float(parts[1].strip())
            temp = float(parts[2].strip())

            resources["gpu"] = {
                "total": int(total_mb * 1024 * 1024),  # Convert to bytes
                "used": int(used_mb * 1024 * 1024),
                "percent": (used_mb / total_mb) * 100 if total_mb > 0 else 0,
                "temperature": int(temp),
            }
    except Exception as e:
        logger.debug(f"GPU info not available: {e}")
        # GPU info not available (not critical)
        resources["gpu"] = {
            "total": 24 * 1024**3,
            "used": 0,
            "percent": 0,
            "temperature": None,
        }

    return resources
