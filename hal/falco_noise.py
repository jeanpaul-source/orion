"""Falco noise filter rules — shared by security.py and watchdog.py.
# why locked: Layer 3 — Falco noise filter; locked with security.py

This module deliberately has ZERO imports from hal.* to keep the watchdog
timer lightweight (no Judge, Executor, or LLM deps load when this is imported).
"""

# Each rule is a (proc_name, fd_name_substring) tuple.
# An event is noise if proc.name matches AND fd.name contains the substring.
NOISE_RULES: list[tuple[str, str]] = [
    # pg_isready polls /etc/shadow — known, benign, extremely noisy
    ("pg_isready", "/etc/shadow"),
    # systemd housekeeping reads /etc/shadow — not interesting
    ("systemd-tmpfile", "/etc/shadow"),
    ("unix_chkpwd", "/etc/shadow"),
    ("systemd-userwork", "/etc/shadow"),
]


def is_falco_noise(event: dict) -> bool:
    """Return True if event matches a known noise rule."""
    fields = event.get("output_fields", {})
    proc = fields.get("proc.name", "")
    fd = fields.get("fd.name", "")
    return any(proc == p and sub in fd for p, sub in NOISE_RULES)
