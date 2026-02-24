"""Prometheus client — query lab metrics and expose lightweight instruments.

This module keeps runtime dependencies minimal and only uses HTTP queries.
It also provides optional metric helpers (no-op when prom pushgateway is absent).
"""
import os
import socket
import threading
import time
from dataclasses import dataclass

import requests


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
                return data["data"]["result"]
        except requests.exceptions.RequestException:
            pass
        return []

    def scalar(self, promql: str) -> float | None:
        result = self.query(promql)
        if result:
            try:
                return float(result[0]["value"][1])
            except (KeyError, IndexError, ValueError):
                pass
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
        load = self.scalar("node_load1")
        swap = self.scalar(
            "(1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes) * 100"
        )
        return {
            "cpu_pct": round(cpu, 1) if cpu is not None else None,
            "mem_pct": round(mem, 1) if mem is not None else None,
            "disk_root_pct": round(disk_root, 1) if disk_root is not None else None,
            "swap_pct": round(swap, 1) if swap is not None else None,
            "load1": round(load, 2) if load is not None else None,
        }


# ----------------------------- Optional instruments ----------------------------- #
_lock = threading.Lock()
_counters: dict[tuple, float] = {}  # (metric_name, frozenset(labels)) → cumulative total
_gauges: dict[tuple, float] = {}    # (metric_name, frozenset(labels)) → last observed value


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
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(dict(labels_fs).items()))
            lines.append(f"{metric}{{{label_str}}} {value}" if label_str else f"{metric} {value}")
        for (metric, labels_fs), value in _gauges.items():
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(dict(labels_fs).items()))
            lines.append(f"{metric}{{{label_str}}} {value}" if label_str else f"{metric} {value}")
    if not lines:
        return
    instance = os.getenv("HAL_INSTANCE", socket.gethostname())
    body = "\n".join(lines) + "\n"
    try:
        requests.post(
            f"{url.rstrip('/')}/metrics/job/hal/instance/{instance}",
            data=body,
            timeout=2,
        )
    except requests.exceptions.RequestException:
        pass


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
