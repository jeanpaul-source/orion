#!/usr/bin/env python3
"""Proactive monitoring watchdog — checks thresholds, sends ntfy alerts.
# why locked: Layer 3/4 — system watchdog; needs test coverage before reactivation

Designed to run as a systemd timer (every 5 minutes). Maintains a cooldown
state file so it doesn't spam the same alert repeatedly.

Usage:
    python -m hal.watchdog
"""

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import requests

import hal.config as cfg
from hal.falco_noise import (
    is_falco_noise,
)
from hal.prometheus import METRIC_PROMQL, PrometheusClient

STATE_FILE = Path.home() / ".orion" / "watchdog_state.json"
LOG_FILE = Path.home() / ".orion" / "watchdog.log"
COOLDOWN_MINUTES = 30
HARVEST_LAST_RUN = Path.home() / ".orion" / "harvest_last_run"
HARVEST_LAG_HOURS = 2
FALCO_LOG = Path("/var/log/falco/events.json")
FALCO_TAIL = 200
_FALCO_ALERT_PRIORITIES = {"Emergency", "Alert", "Critical", "Error", "Warning"}

# metric_key: (threshold, label, urgency, unit)
THRESHOLDS: dict[str, tuple[float, str, str, str]] = {
    "cpu_pct": (85.0, "CPU usage", "default", "%"),
    "mem_pct": (90.0, "Memory usage", "high", "%"),
    "disk_root_pct": (85.0, "Disk / usage", "high", "%"),
    "disk_docker_pct": (85.0, "Disk /docker usage", "high", "%"),
    "disk_data_pct": (85.0, "Disk /data/projects usage", "high", "%"),
    "swap_pct": (80.0, "Swap usage", "urgent", "%"),
    "load1": (16.0, "Load average", "default", ""),  # 16 on a 20-core machine
    "gpu_vram_pct": (95.0, "GPU VRAM usage", "urgent", "%"),
    "gpu_temp_c": (
        83.0,
        "GPU temperature",
        "urgent",
        "\u00b0C",
    ),  # 3090 Ti throttle point
}


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _in_cooldown(state: dict, key: str) -> bool:
    last = state.get(key)
    if not last:
        return False
    last_dt = datetime.fromisoformat(last)
    return datetime.now() - last_dt < timedelta(minutes=COOLDOWN_MINUTES)


def _send_ntfy(ntfy_url: str, alerts: list[tuple[str, float, float, str, str]]) -> bool:
    """Send a bundled ntfy notification. Returns True on success."""
    if not ntfy_url:
        return False

    lines = []
    max_urgency = "default"
    urgency_order = {"default": 0, "high": 1, "urgent": 2}
    for label, value, threshold, urgency, unit in alerts:
        lines.append(f"{label}: {value:.1f}{unit} (threshold: {threshold:.0f}{unit})")
        if urgency_order.get(urgency, 0) > urgency_order.get(max_urgency, 0):
            max_urgency = urgency

    body = "\n".join(lines)
    try:
        r = requests.post(
            ntfy_url,
            data=body.encode(),
            headers={
                "Title": "Orion Alert — the-lab",
                "Priority": max_urgency,
                "Tags": "warning,server",
            },
            timeout=10,
        )
        return r.status_code < 300
    except requests.exceptions.RequestException:
        return False


def _log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts}  {msg}\n")


def _check_ntp(**_kw: object) -> str | None:
    """Returns an alert message if NTP is not synchronized, else None."""
    try:
        out = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if out == "NTPSynchronized=no":
            return "NTP not synchronized — clock may drift"
    except Exception:
        pass
    return None


def _check_harvest(**_kw: object) -> str | None:
    """Returns an alert message if harvest_last_run is missing or stale."""
    try:
        mtime = HARVEST_LAST_RUN.stat().st_mtime
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        if age_hours > HARVEST_LAG_HOURS:
            return f"Harvest stale: last run {age_hours:.1f}h ago (threshold: {HARVEST_LAG_HOURS}h)"
    except FileNotFoundError:
        return "Harvest has never run (no harvest_last_run file)"
    except Exception:
        pass
    return None


def _send_ntfy_simple(
    ntfy_url: str,
    messages: list[str],
    urgency: str = "high",
    title: str = "Orion Alert — the-lab",
    tags: str = "warning,server",
) -> bool:
    """Send a free-form ntfy notification for non-metric alerts. Returns True on success."""
    if not ntfy_url:
        return False
    body = "\n".join(messages)
    try:
        r = requests.post(
            ntfy_url,
            data=body.encode(),
            headers={
                "Title": title,
                "Priority": urgency,
                "Tags": tags,
            },
            timeout=10,
        )
        return r.status_code < 300
    except requests.exceptions.RequestException:
        return False


CRITICAL_CONTAINERS: set[str] = {
    "prometheus",
    "grafana",
    "pgvector-kb",
    "ntopng",
    "pushgateway",
}

# Metrics to watch for rate-of-change: (METRIC_PROMQL key, Config attr, human label)
# CPU and load are excluded — too spiky for rate-of-change alerting.
TREND_METRICS: list[tuple[str, str, str]] = [
    ("disk_root", "watchdog_disk_rate_pct_per_hour", "Disk / usage"),
    ("disk_docker", "watchdog_disk_rate_pct_per_hour", "Disk /docker usage"),
    ("disk_data", "watchdog_disk_rate_pct_per_hour", "Disk /data/projects usage"),
    ("mem", "watchdog_mem_rate_pct_per_hour", "Memory usage"),
    ("swap", "watchdog_swap_rate_pct_per_hour", "Swap usage"),
    ("gpu_vram", "watchdog_gpu_vram_rate_pct_per_hour", "GPU VRAM usage"),
]


def _check_containers(**_kw: object) -> str | None:
    """Returns an alert message if any critical container is exited/dead, else None."""
    try:
        out = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "status=exited",
                "--filter",
                "status=dead",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if not out:
            return None
        stopped = set(out.splitlines())
        down = CRITICAL_CONTAINERS & stopped
        if down:
            names = ", ".join(sorted(down))
            return f"Critical containers down: {names}"
    except Exception:
        pass
    return None


def _check_trends(
    prom: PrometheusClient,
    config: object,
    state: dict | None = None,
    **_kw: object,
) -> str | None:
    """Returns an alert message if any watched metric is rising faster than its
    configured rate threshold (proactive — fires before the hard threshold is hit)."""
    firing: list[str] = []
    for promql_key, cfg_attr, human_label in TREND_METRICS:
        promql = METRIC_PROMQL.get(promql_key, "")
        if not promql:
            continue
        threshold: float = getattr(config, cfg_attr, 5.0)
        try:
            summary = prom.trend(promql, "1h")
        except Exception:
            continue
        if summary is None:
            continue
        if summary["direction"] == "rising" and summary["delta_per_hour"] >= threshold:
            firing.append(
                f"{human_label} trending +{summary['delta_per_hour']:.1f}%/hr"
                f" (threshold: {threshold:.0f}%/hr)"
            )
    if not firing:
        return None
    count = len(firing)
    header = f"{count} metric{'s' if count != 1 else ''} trending toward threshold"
    return header + ":\n" + "\n".join(firing)


def _check_falco(state: dict | None = None, **_kw: object) -> str | None:
    """Returns alert message if new high-priority Falco events found, else None.

    Tracks ``falco_last_seen`` in *state* so the same events are not re-alerted
    on the next timer run.
    """
    if not FALCO_LOG.exists():
        return None
    try:
        out = subprocess.run(
            ["tail", "-n", str(FALCO_TAIL), str(FALCO_LOG)],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return None

    last_seen = (state or {}).get("falco_last_seen", "")
    newest_time = last_seen

    events: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_falco_noise(event):
            continue
        priority = event.get("priority", "")
        if priority not in _FALCO_ALERT_PRIORITIES:
            continue
        event_time = event.get("time", "")
        if last_seen and event_time <= last_seen:
            continue
        if event_time > newest_time:
            newest_time = event_time
        events.append(event)

    # Persist high-water mark so next run skips these events
    if state is not None and newest_time:
        state["falco_last_seen"] = newest_time

    if not events:
        return None

    lines: list[str] = []
    for e in events[:10]:
        rule = e.get("rule", "unknown")
        pri = e.get("priority", "?")
        proc = e.get("output_fields", {}).get("proc.name", "?")
        lines.append(f"[{pri}] {rule} (proc: {proc})")
    count = len(events)
    if count > 10:
        lines.append(f"... and {count - 10} more")
    header = f"{count} Falco security event{'s' if count != 1 else ''}"
    return f"{header}:\n" + "\n".join(lines)


def run() -> None:
    config = cfg.load()

    if not config.ntfy_url:
        _log(
            "INFO   NTFY_URL is not set — all alerts will be logged only, no push notifications."
        )

    prom = PrometheusClient(config.prometheus_url)

    try:
        metrics = prom.health()
    except Exception as e:
        _log(f"WARNING: Prometheus unreachable — metric alerts suspended: {e}")
        _send_ntfy_simple(
            config.ntfy_url,
            ["Watchdog: Prometheus unreachable — metric alerts suspended."],
            urgency="low",
            title="Orion Watchdog Warning — the-lab",
            tags="warning,server",
        )
        sys.exit(0)

    state = _load_state()
    alerts: list[
        tuple[str, float, float, str, str]
    ] = []  # (label, value, threshold, urgency, unit)
    fired: list[str] = []

    for key, (threshold, label, urgency, unit) in THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if value >= threshold:
            if not _in_cooldown(state, key):
                alerts.append((label, value, threshold, urgency, unit))
                fired.append(key)
                _log(f"ALERT  {key}={value:.1f} (>={threshold:.0f})")
        else:
            # Clear cooldown when metric recovers
            if key in state:
                del state[key]
                _log(f"CLEAR  {key}={value:.1f}")
                _send_ntfy_simple(
                    config.ntfy_url,
                    [
                        f"{label} recovered: {value:.1f}{unit} (threshold: {threshold:.0f}{unit})"
                    ],
                    urgency="low",
                    title="Orion RESOLVED \u2014 the-lab",
                    tags="white_check_mark,server",
                )

    if alerts:
        ok = _send_ntfy(config.ntfy_url, alerts)
        if ok:
            _log(f"ntfy sent: {', '.join(fired)}")
        else:
            _log(
                f"ntfy FAILED (url={'set' if config.ntfy_url else 'not set'}): {', '.join(fired)}"
            )
        # Update state with alert timestamps
        now = datetime.now().isoformat(timespec="seconds")
        for key in fired:
            state[key] = now

    # Boolean / time-based checks (NTP, harvest lag)
    simple_alerts: list[str] = []
    simple_fired: list[str] = []
    simple_checks: list[tuple[str, Callable[..., str | None], str]] = [
        ("ntp", _check_ntp, "urgent"),
        ("harvest_lag", _check_harvest, "high"),
        ("containers", _check_containers, "urgent"),
        ("falco", _check_falco, "urgent"),
        ("trend", _check_trends, "high"),
    ]
    for key, check_fn, urgency in simple_checks:
        msg = check_fn(state=state, prom=prom, config=config)
        if msg:
            if not _in_cooldown(state, key):
                simple_alerts.append(msg)
                simple_fired.append(key)
                _log(f"ALERT  {key}: {msg}")
        else:
            if key in state:
                del state[key]
                _log(f"CLEAR  {key}")
                _send_ntfy_simple(
                    config.ntfy_url,
                    [f"{key} resolved"],
                    urgency="low",
                    title="Orion RESOLVED \u2014 the-lab",
                    tags="white_check_mark,server",
                )

    if simple_alerts:
        ok = _send_ntfy_simple(config.ntfy_url, simple_alerts)
        if ok:
            _log(f"ntfy sent: {', '.join(simple_fired)}")
        else:
            _log(
                f"ntfy FAILED (url={'set' if config.ntfy_url else 'not set'}): {', '.join(simple_fired)}"
            )
        now = datetime.now().isoformat(timespec="seconds")
        for key in simple_fired:
            state[key] = now

    _save_state(state)


if __name__ == "__main__":
    run()
