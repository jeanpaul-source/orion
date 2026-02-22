"""Prometheus client — query lab metrics."""
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
        return {
            "cpu_pct": round(cpu, 1) if cpu is not None else None,
            "mem_pct": round(mem, 1) if mem is not None else None,
            "disk_root_pct": round(disk_root, 1) if disk_root is not None else None,
            "load1": round(load, 2) if load is not None else None,
        }
