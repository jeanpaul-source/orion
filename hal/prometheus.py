"""Prometheus client — query lab metrics and expose lightweight instruments.

This module keeps runtime dependencies minimal and only uses HTTP queries.
It also provides optional metric helpers (no-op when prom pushgateway is absent).
"""

import contextlib
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, cast

import requests

log = logging.getLogger(__name__)


class PrometheusClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def query(self, promql: str) -> list:
        try:
            r = requests.get(
                f"{self.base_url}/api/v1/query",
                params={"query": promql},
                timeout=5,
            )
            data = r.json()
            if data.get("status") == "success":
                return cast(list[Any], data["data"]["result"])
        except requests.exceptions.RequestException as exc:
            log.warning("Prometheus query failed: %s", exc)
        return []

    def scalar(self, promql: str) -> float | None:
        result = self.query(promql)
        if result:
            try:
                return float(result[0]["value"][1])
            except (KeyError, IndexError, ValueError) as exc:
                log.warning("Prometheus scalar parse failed: %s", exc)
        return None

    def health(self) -> dict:
        cpu = self.scalar(
            '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
        )
        mem = self.scalar(
            "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100"
        )
        disk_root = self.scalar(
            '(1 - node_filesystem_avail_bytes{mountpoint="/"} '
            '/ node_filesystem_size_bytes{mountpoint="/"}) * 100'
        )
        disk_docker = self.scalar(
            '(1 - node_filesystem_avail_bytes{mountpoint="/docker"} '
            '/ node_filesystem_size_bytes{mountpoint="/docker"}) * 100'
        )
        disk_data = self.scalar(
            '(1 - node_filesystem_avail_bytes{mountpoint="/data/projects"} '
            '/ node_filesystem_size_bytes{mountpoint="/data/projects"}) * 100'
        )
        load = self.scalar("node_load1")
        swap = self.scalar(
            "(1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes) * 100"
        )
        gpu_vram = self.scalar('node_gpu_vram_usage_percent{gpu="0"}')
        gpu_temp = self.scalar('node_gpu_temperature_celsius{gpu="0"}')
        return {
            "cpu_pct": round(cpu, 1) if cpu is not None else None,
            "mem_pct": round(mem, 1) if mem is not None else None,
            "disk_root_pct": round(disk_root, 1) if disk_root is not None else None,
            "disk_docker_pct": round(disk_docker, 1)
            if disk_docker is not None
            else None,
            "disk_data_pct": round(disk_data, 1) if disk_data is not None else None,
            "swap_pct": round(swap, 1) if swap is not None else None,
            "load1": round(load, 2) if load is not None else None,
            "gpu_vram_pct": round(gpu_vram, 1) if gpu_vram is not None else None,
            "gpu_temp_c": round(gpu_temp, 1) if gpu_temp is not None else None,
        }

    def range_query(
        self,
        promql: str,
        start: float,
        end: float,
        step: float,
    ) -> list[tuple[float, float]]:
        """Query /api/v1/query_range and return the first series as (timestamp, value) tuples.

        Returns an empty list on any error, HTTP failure, or empty result — same
        defensive pattern as query().
        """
        try:
            r = requests.get(
                f"{self.base_url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": str(start),
                    "end": str(end),
                    "step": str(step),
                },
                timeout=10,
            )
            data: Any = r.json()
            if data.get("status") == "success":
                result = data["data"]["result"]
                if result:
                    return [(float(ts), float(val)) for ts, val in result[0]["values"]]
        except (
            requests.exceptions.RequestException,
            KeyError,
            ValueError,
            IndexError,
            TypeError,
        ) as exc:
            log.warning("Prometheus range query failed: %s", exc)
        return []

    def trend(
        self,
        promql: str,
        window: str = "1h",
    ) -> dict[str, Any] | None:
        """Return a summary dict describing how a metric moved over the given window.

        Parameters
        ----------
        promql:
            Any valid PromQL instant expression (the same strings used in health()).
        window:
            Lookback duration string — "1h", "6h", or "24h".  Any string ending in
            "h" with an integer prefix is accepted; anything else is treated as 1h.

        Returns
        -------
        dict with keys: first, last, min, max, delta, delta_per_hour, direction
            direction is "rising", "falling", or "stable".
        None if fewer than 2 data points are returned (metric unavailable or too
            short a window for the scrape interval).
        """
        # Parse window string → seconds
        window_seconds = 3600  # default 1h
        try:
            if window.endswith("h"):
                window_seconds = int(window[:-1]) * 3600
            elif window.endswith("m"):
                window_seconds = int(window[:-1]) * 60
        except ValueError:
            pass
        # Cap at 24h; ensure at least 5 minutes
        window_seconds = max(300, min(window_seconds, 86400))

        now = time.time()
        start = now - window_seconds
        # Target ~60 data points regardless of window length
        step = max(15, window_seconds // 60)

        points = self.range_query(promql, start=start, end=now, step=step)
        if len(points) < 2:
            return None

        values = [v for _, v in points]
        first = values[0]
        last = values[-1]
        mn = min(values)
        mx = max(values)
        delta = last - first
        hours = window_seconds / 3600
        delta_per_hour = delta / hours if hours > 0 else 0.0

        # Stable band: delta must exceed 0.5% of the observed range (or 0.1 absolute)
        # to count as rising/falling — avoids noise calling flat metrics as trending.
        value_range = mx - mn
        threshold = max(value_range * 0.005, 0.1)
        if delta > threshold:
            direction = "rising"
        elif delta < -threshold:
            direction = "falling"
        else:
            direction = "stable"

        return {
            "first": round(first, 2),
            "last": round(last, 2),
            "min": round(mn, 2),
            "max": round(mx, 2),
            "delta": round(delta, 2),
            "delta_per_hour": round(delta_per_hour, 2),
            "direction": direction,
        }


# ----------------------------- Named metric → PromQL map ----------------------------- #
# Single source of truth for metric name → PromQL expression.
# Used by the get_trend agent tool (hal/tools.py) and the proactive watchdog
# (hal/watchdog.py).  Both import from here so there is no duplication.
METRIC_PROMQL: dict[str, str] = {
    "cpu": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
    "mem": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
    "disk_root": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/"}'
        ' / node_filesystem_size_bytes{mountpoint="/"}) * 100'
    ),
    "disk_docker": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/docker"}'
        ' / node_filesystem_size_bytes{mountpoint="/docker"}) * 100'
    ),
    "disk_data": (
        '(1 - node_filesystem_avail_bytes{mountpoint="/data/projects"}'
        ' / node_filesystem_size_bytes{mountpoint="/data/projects"}) * 100'
    ),
    "swap": "(1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes) * 100",
    "load": "node_load1",
    "gpu_vram": 'node_gpu_vram_usage_percent{gpu="0"}',
    "gpu_temp": 'node_gpu_temperature_celsius{gpu="0"}',
}


# ----------------------------- Optional instruments ----------------------------- #
_lock = threading.Lock()
_counters: dict[
    tuple, float
] = {}  # (metric_name, frozenset(labels)) → cumulative total
_gauges: dict[
    tuple, float
] = {}  # (metric_name, frozenset(labels)) → last observed value


@dataclass
class Counter:
    name: str
    labels: tuple[str, ...] = ()

    def inc(self, **label_values: str) -> None:
        key = (self.name, frozenset(label_values.items()))
        with _lock:
            _counters[key] = _counters.get(key, 0) + 1


@dataclass
class Histogram:
    name: str
    labels: tuple[str, ...] = ()

    def observe(self, value: float, **label_values: str) -> None:
        key = (self.name, frozenset(label_values.items()))
        with _lock:
            _gauges[key] = value


def flush_metrics() -> None:
    """Push all accumulated metrics to Pushgateway in one request.

    Each Counter value is the cumulative total since process start.
    Each Histogram value is the most recently observed sample.
    All metrics are batched into a single POST so they don't clobber each other.
    No-op if PROM_PUSHGATEWAY is not set.
    """
    url = os.getenv("PROM_PUSHGATEWAY")
    if not url:
        return
    with _lock:
        lines: list[str] = []
        for (metric, labels_fs), value in _counters.items():
            label_str = ",".join(
                f'{k}="{v}"' for k, v in sorted(dict(labels_fs).items())
            )
            lines.append(
                f"{metric}{{{label_str}}} {value}" if label_str else f"{metric} {value}"
            )
        for (metric, labels_fs), value in _gauges.items():
            label_str = ",".join(
                f'{k}="{v}"' for k, v in sorted(dict(labels_fs).items())
            )
            lines.append(
                f"{metric}{{{label_str}}} {value}" if label_str else f"{metric} {value}"
            )
    if not lines:
        return
    instance = os.getenv("HAL_INSTANCE", socket.gethostname())
    body = "\n".join(lines) + "\n"
    with contextlib.suppress(requests.exceptions.RequestException):
        requests.post(
            f"{url.rstrip('/')}/metrics/job/hal/instance/{instance}",
            data=body,
            timeout=2,
        )


def start_metrics_heartbeat(interval_seconds: int = 30) -> None:
    """Spawn a daemon thread that calls flush_metrics() every interval_seconds.

    Starts only if PROM_PUSHGATEWAY is configured. The thread is a daemon so
    it exits automatically when the process exits — no cleanup required.
    Call once at process startup (main.py and server.py).
    """
    if not os.getenv("PROM_PUSHGATEWAY"):
        return

    def _loop() -> None:
        while True:
            time.sleep(interval_seconds)
            flush_metrics()

    t = threading.Thread(target=_loop, daemon=True, name="metrics-heartbeat")
    t.start()
