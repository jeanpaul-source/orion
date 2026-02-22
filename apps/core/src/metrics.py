"""
Prometheus Metrics for ORION Core

Instruments ORION with metrics for monitoring via Prometheus and Grafana.

Metrics Categories:
- Request metrics (total, duration, status)
- Subsystem metrics (knowledge, action, learning, watch)
- Queue metrics (size, wait time, throughput)
- Session metrics (active, created, destroyed)
- System metrics (memory, CPU, threads)

Author: ORION Project
Date: November 17, 2025
"""

import logging
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
import psutil
import os

logger = logging.getLogger(__name__)

# ============================================================================
# REQUEST METRICS
# ============================================================================

# Total requests by subsystem and status
requests_total = Counter(
    'orion_requests_total',
    'Total requests processed by ORION',
    ['subsystem', 'status']
)

# Request duration by subsystem
request_duration = Histogram(
    'orion_request_duration_seconds',
    'Request processing duration in seconds',
    ['subsystem'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf"))
)

# Active requests (currently processing)
active_requests = Gauge(
    'orion_active_requests',
    'Currently active requests',
    ['subsystem']
)

# ============================================================================
# SUBSYSTEM METRICS
# ============================================================================

# Knowledge subsystem
knowledge_queries = Counter(
    'orion_knowledge_queries_total',
    'Total knowledge base queries',
    ['source']  # anythingllm, qdrant, etc.
)

knowledge_query_duration = Histogram(
    'orion_knowledge_query_duration_seconds',
    'Knowledge query duration',
    ['source'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf"))
)

# Action subsystem
action_executions = Counter(
    'orion_action_executions_total',
    'Total action executions',
    ['tool', 'status']  # tool=docker/ssh/git, status=success/failed
)

action_duration = Histogram(
    'orion_action_duration_seconds',
    'Action execution duration',
    ['tool'],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, float("inf"))
)

# Learning subsystem
learning_tasks = Counter(
    'orion_learning_tasks_total',
    'Total learning tasks',
    ['task_type', 'status']  # harvest/process/embed, success/failed
)

# Watch subsystem
watch_checks = Counter(
    'orion_watch_checks_total',
    'Total monitoring checks',
    ['check_type', 'status']  # disk/memory/cpu/gpu, ok/warning/critical
)

# ============================================================================
# QUEUE METRICS
# ============================================================================

queue_size = Gauge(
    'orion_queue_size',
    'Current request queue size'
)

queue_wait_time = Histogram(
    'orion_queue_wait_time_seconds',
    'Time spent waiting in queue',
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf"))
)

queue_rejections = Counter(
    'orion_queue_rejections_total',
    'Total requests rejected due to full queue'
)

# ============================================================================
# SESSION METRICS
# ============================================================================

active_sessions = Gauge(
    'orion_active_sessions',
    'Currently active conversation sessions'
)

sessions_created = Counter(
    'orion_sessions_created_total',
    'Total sessions created'
)

sessions_destroyed = Counter(
    'orion_sessions_destroyed_total',
    'Total sessions destroyed',
    ['reason']  # expired/manual/error
)

session_duration = Histogram(
    'orion_session_duration_seconds',
    'Session lifetime duration',
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800, 86400, float("inf"))
)

# ============================================================================
# SYSTEM METRICS
# ============================================================================

system_memory_bytes = Gauge(
    'orion_system_memory_bytes',
    'System memory usage in bytes',
    ['type']  # total/available/used
)

system_cpu_percent = Gauge(
    'orion_system_cpu_percent',
    'System CPU usage percentage'
)

orion_info = Info(
    'orion_info',
    'ORION build information'
)

# ============================================================================
# DECORATORS FOR AUTOMATIC INSTRUMENTATION
# ============================================================================

def track_request(subsystem: str):
    """
    Decorator to automatically track request metrics.

    Usage:
        @track_request("knowledge")
        async def handle_knowledge_query(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            active_requests.labels(subsystem=subsystem).inc()
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                requests_total.labels(subsystem=subsystem, status="success").inc()
                return result

            except Exception as e:
                requests_total.labels(subsystem=subsystem, status="failed").inc()
                raise

            finally:
                duration = time.time() - start_time
                request_duration.labels(subsystem=subsystem).observe(duration)
                active_requests.labels(subsystem=subsystem).dec()

        return wrapper
    return decorator


def track_action(tool: str):
    """
    Decorator to track action execution metrics.

    Usage:
        @track_action("docker")
        async def docker_ps(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                action_executions.labels(tool=tool, status="success").inc()
                return result

            except Exception as e:
                action_executions.labels(tool=tool, status="failed").inc()
                raise

            finally:
                duration = time.time() - start_time
                action_duration.labels(tool=tool).observe(duration)

        return wrapper
    return decorator


# ============================================================================
# SYSTEM METRICS COLLECTOR
# ============================================================================

def update_system_metrics():
    """
    Update system metrics (called periodically).

    Should be called every 15-30 seconds to keep metrics fresh.
    """
    try:
        # Memory metrics
        mem = psutil.virtual_memory()
        system_memory_bytes.labels(type="total").set(mem.total)
        system_memory_bytes.labels(type="available").set(mem.available)
        system_memory_bytes.labels(type="used").set(mem.used)

        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        system_cpu_percent.set(cpu_percent)

    except Exception as e:
        logger.error(f"Failed to update system metrics: {e}")


def set_build_info(version: str, environment: str):
    """
    Set ORION build information.

    Call this once at startup.
    """
    orion_info.info({
        'version': version,
        'environment': environment,
        'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    })


# ============================================================================
# METRICS ENDPOINT
# ============================================================================

def get_metrics() -> tuple[bytes, str]:
    """
    Get Prometheus metrics in text format.

    Returns:
        (metrics_bytes, content_type)
    """
    # Update system metrics before returning
    update_system_metrics()

    return generate_latest(), CONTENT_TYPE_LATEST
