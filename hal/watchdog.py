#!/usr/bin/env python3
"""Proactive monitoring watchdog — checks thresholds, sends ntfy alerts.

Designed to run as a systemd timer (every 5 minutes). Maintains a cooldown
state file so it doesn't spam the same alert repeatedly.

Usage:
    python -m hal.watchdog
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

import hal.config as cfg
from hal.prometheus import PrometheusClient

STATE_FILE = Path.home() / ".orion" / "watchdog_state.json"
LOG_FILE = Path.home() / ".orion" / "watchdog.log"
COOLDOWN_MINUTES = 30
HARVEST_LAST_RUN = Path.home() / ".orion" / "harvest_last_run"
HARVEST_LAG_HOURS = 2

# metric_key: (threshold, label, urgency)
THRESHOLDS: dict[str, tuple[float, str, str]] = {
    "cpu_pct": (85.0, "CPU usage", "default"),
    "mem_pct": (90.0, "Memory usage", "high"),
    "disk_root_pct": (85.0, "Disk / usage", "high"),
    "swap_pct": (80.0, "Swap usage", "urgent"),
    "load1": (16.0, "Load average", "default"),  # 16 on a 20-core machine
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


def _send_ntfy(ntfy_url: str, alerts: list[tuple[str, float, float, str]]) -> bool:
    """Send a bundled ntfy notification. Returns True on success."""
    if not ntfy_url:
        return False

    lines = []
    max_urgency = "default"
    urgency_order = {"default": 0, "high": 1, "urgent": 2}
    for label, value, threshold, urgency in alerts:
        lines.append(f"{label}: {value:.1f}% (threshold: {threshold:.0f}%)")
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


def _check_ntp() -> str | None:
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


def _check_harvest() -> str | None:
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
    ntfy_url: str, messages: list[str], urgency: str = "high"
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
                "Title": "Orion Alert — the-lab",
                "Priority": urgency,
                "Tags": "warning,server",
            },
            timeout=10,
        )
        return r.status_code < 300
    except requests.exceptions.RequestException:
        return False


def run() -> None:
    config = cfg.load()
    prom = PrometheusClient(config.prometheus_url)

    try:
        metrics = prom.health()
    except Exception as e:
        _log(f"ERROR: could not reach Prometheus — {e}")
        sys.exit(0)  # not an alert-worthy failure, just unavailable

    state = _load_state()
    alerts: list[
        tuple[str, float, float, str]
    ] = []  # (label, value, threshold, urgency)
    fired: list[str] = []

    for key, (threshold, label, urgency) in THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if value >= threshold:
            if not _in_cooldown(state, key):
                alerts.append((label, value, threshold, urgency))
                fired.append(key)
                _log(f"ALERT  {key}={value:.1f} (>={threshold:.0f})")
        else:
            # Clear cooldown when metric recovers
            if key in state:
                del state[key]
                _log(f"CLEAR  {key}={value:.1f}")

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
    for key, check_fn, urgency in [
        ("ntp", _check_ntp, "urgent"),
        ("harvest_lag", _check_harvest, "high"),
    ]:
        msg = check_fn()
        if msg:
            if not _in_cooldown(state, key):
                simple_alerts.append(msg)
                simple_fired.append(key)
                _log(f"ALERT  {key}: {msg}")
        else:
            if key in state:
                del state[key]
                _log(f"CLEAR  {key}")

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
