"""Shared notification helpers — ntfy push notifications.

Extracted from ``hal.watchdog`` so that both the watchdog and the HTTP
server (recovery notifications) can send ntfy messages without duplicating
the transport logic.
"""

from __future__ import annotations

import requests


def send_ntfy_simple(
    ntfy_url: str,
    messages: list[str],
    urgency: str = "high",
    title: str = "Orion Alert — the-lab",
    tags: str = "warning,server",
) -> bool:
    """Send a free-form ntfy notification. Returns True on success.

    Parameters
    ----------
    ntfy_url:
        Full ntfy topic URL (e.g. ``https://ntfy.sh/orion-alerts``).
    messages:
        Lines to join into the notification body.
    urgency:
        ntfy priority string (``default``, ``high``, ``urgent``).
    title:
        Notification title.
    tags:
        Comma-separated ntfy tag string.
    """
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
