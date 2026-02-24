"""Prometheus client — query lab metrics and expose lightweight instruments.

This module keeps runtime dependencies minimal and only uses HTTP queries.
It also provides optional metric helpers (no-op when prom pushgateway is absent).
"""
import os
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


# ---------------------------- Optional instruments ---------------------------- #
@dataclass
class Counter:
    name: str
    labels: tuple[str, ...] = ()

    def inc(self, **label_values: str) -> None:  # no-op placeholder
        _push_metric(self.name, 1, label_values)


@dataclass
class Histogram:
    name: str
    labels: tuple[str, ...] = ()

    def observe(self, value: float, **label_values: str) -> None:  # no-op placeholder
        _push_metric(self.name, value, label_values)


def _push_metric(metric: str, value: float, labels: dict[str, str]) -> None:
    # Lightweight push to a pushgateway if configured; otherwise no-op.
    url = os.getenv("PROM_PUSHGATEWAY")
    if not url:
        return
    try:
        # Build a simple line for the text format
        label_str = ",".join(f"{k}=\"{v}\"" for k, v in sorted(labels.items()))
        line = f"{metric}{{{label_str}}} {value}\n" if label_str else f"{metric} {value}\n"
        requests.post(f"{url.rstrip('/')}/metrics/job/hal", data=line, timeout=2)
    except requests.exceptions.RequestException:
        pass
