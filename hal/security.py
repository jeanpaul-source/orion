"""Security workers — read Falco alerts, Osquery host state, ntopng traffic,
and run Nmap LAN scans.

All read operations are tier 0 (auto-approved).  scan_lan is tier 1 (active
probe — prompts the user before running).

Worker signature mirrors hal/workers.py:
    func(..., executor: SSHExecutor, judge: Judge, reason: str = "") -> result
"""

from __future__ import annotations

import json
import shlex
import xml.etree.ElementTree as ET

from hal.executor import SSHExecutor
from hal.judge import Judge

# ---------------------------------------------------------------------------
# Noise filters for Falco events
# Each filter is a callable (event_dict) -> bool.  Return True to DROP.
# ---------------------------------------------------------------------------

_FALCO_NOISE: list = [
    # pg_isready polls /etc/shadow — known, benign, extremely noisy
    lambda e: (
        e.get("output_fields", {}).get("proc.name") == "pg_isready"
        and "/etc/shadow" in e.get("output_fields", {}).get("fd.name", "")
    ),
    # systemd-tmpfile reads /etc/shadow on boot — not interesting
    lambda e: (
        e.get("output_fields", {}).get("proc.name")
        in ("systemd-tmpfile", "unix_chkpwd")
        and "/etc/shadow" in e.get("output_fields", {}).get("fd.name", "")
    ),
]


def _is_noise(event: dict) -> bool:
    return any(f(event) for f in _FALCO_NOISE)


# ---------------------------------------------------------------------------
# 1. Falco security events
# ---------------------------------------------------------------------------


def get_security_events(
    executor: SSHExecutor,
    judge: Judge,
    n: int = 50,
    reason: str = "",
) -> list[dict]:
    """Return the last *n* Falco events, with known-noisy rules filtered out.

    Each returned dict has: time, rule, priority, proc_name, fd_name, output.
    Returns an empty list on any failure.
    """
    if not judge.approve(
        "get_security_events", f"tail -n {n} /var/log/falco/events.json", reason=reason
    ):
        return []

    result = executor.run(f"tail -n {shlex.quote(str(n))} /var/log/falco/events.json")
    if result["returncode"] != 0:
        stderr = result.get("stderr", "").strip()
        return [{"error": f"Falco log read failed: {stderr}"}]

    events: list[dict] = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _is_noise(event):
            continue
        fields = event.get("output_fields", {})
        events.append(
            {
                "time": event.get("time", ""),
                "rule": event.get("rule", ""),
                "priority": event.get("priority", ""),
                "proc_name": fields.get("proc.name", ""),
                "fd_name": fields.get("fd.name", ""),
                "output": event.get("output", ""),
            }
        )

    return events


# ---------------------------------------------------------------------------
# 2. Host connections via Osquery
# ---------------------------------------------------------------------------

_LISTENING_SQL = (
    "SELECT p.name, l.port, l.address, l.protocol "
    "FROM listening_ports l "
    "LEFT JOIN processes p ON l.pid = p.pid "
    "WHERE l.port > 0 "
    "ORDER BY l.port"
)

_ESTABLISHED_SQL = (
    "SELECT p.name, s.local_port, s.remote_address, s.remote_port "
    "FROM process_open_sockets s "
    "LEFT JOIN processes p ON s.pid = p.pid "
    "WHERE s.state = 'ESTABLISHED'"
)

_ARP_SQL = "SELECT * FROM arp_cache"


def get_host_connections(
    executor: SSHExecutor,
    judge: Judge,
    reason: str = "",
) -> dict:
    """Return listening ports and established connections from Osquery.

    Returns a dict:
        {
            "listening":     [ {name, port, address, protocol}, ... ],
            "connections":   [ {name, local_port, remote_address, remote_port}, ... ],
            "arp":           [ {address, mac, interface, permanent}, ... ],
        }
    """
    if not judge.approve(
        "get_host_connections",
        "osqueryi: listening_ports, process_open_sockets, arp_cache",
        reason=reason,
    ):
        return {}

    def _run_query(sql: str) -> list[dict] | str:
        cmd = f"sudo osqueryi --json {shlex.quote(sql)}"
        r = executor.run(cmd)
        if r["returncode"] != 0:
            return f"query failed: {r.get('stderr', '').strip()}"
        try:
            return json.loads(r["stdout"])
        except json.JSONDecodeError as exc:
            return f"json parse error: {exc}"

    return {
        "listening": _run_query(_LISTENING_SQL),
        "connections": _run_query(_ESTABLISHED_SQL),
        "arp": _run_query(_ARP_SQL),
    }


# ---------------------------------------------------------------------------
# 3. ntopng traffic summary
# ---------------------------------------------------------------------------


def get_traffic_summary(
    executor: SSHExecutor,
    judge: Judge,
    ntopng_url: str = "http://localhost:3000",
    top_flows: int = 20,
    reason: str = "",
) -> dict:
    """Return aggregate interface stats and top active flows from ntopng.

    Returns a dict:
        {
            "interface":  { bytes_sent, bytes_rcvd, num_hosts, num_flows, ... },
            "top_flows":  [ {src_ip, src_port, dst_ip, dst_port, bytes, ...}, ... ],
        }
    """
    if not judge.approve(
        "get_traffic_summary", f"ntopng REST at {ntopng_url}", reason=reason
    ):
        return {}

    iface_url = f"{ntopng_url}/lua/rest/v2/get/interface/data.lua?ifid=0"
    flows_url = (
        f"{ntopng_url}/lua/rest/v2/get/flow/active.lua?ifid=0&perPage={top_flows}"
    )

    def _curl(url: str) -> dict | list | str:
        r = executor.run(f"curl -s {shlex.quote(url)}")
        if r["returncode"] != 0:
            return f"curl failed: {r.get('stderr', '').strip()}"
        try:
            return json.loads(r["stdout"])
        except json.JSONDecodeError as exc:
            return f"json parse error: {exc}"

    return {
        "interface": _curl(iface_url),
        "top_flows": _curl(flows_url),
    }


# ---------------------------------------------------------------------------
# 4. Nmap LAN scan
# ---------------------------------------------------------------------------


def _parse_nmap_xml(xml_text: str) -> list[dict]:
    """Extract host records from nmap XML output.

    Returns a list of dicts with: ip, mac, mac_vendor, status.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [{"error": "could not parse nmap XML"}]

    hosts: list[dict] = []
    for host in root.findall("host"):
        status_el = host.find("status")
        state = (
            status_el.attrib.get("state", "unknown")
            if status_el is not None
            else "unknown"
        )

        ip = mac = vendor = ""
        for addr in host.findall("address"):
            atype = addr.attrib.get("addrtype", "")
            if atype == "ipv4":
                ip = addr.attrib.get("addr", "")
            elif atype == "mac":
                mac = addr.attrib.get("addr", "")
                vendor = addr.attrib.get("vendor", "")

        # hostname (if resolved by nmap)
        hostname = ""
        hostnames_el = host.find("hostnames")
        if hostnames_el is not None:
            hn = hostnames_el.find("hostname")
            if hn is not None:
                hostname = hn.attrib.get("name", "")

        hosts.append(
            {
                "ip": ip,
                "mac": mac,
                "mac_vendor": vendor,
                "hostname": hostname,
                "status": state,
            }
        )
    return hosts


def scan_lan(
    subnet: str,
    executor: SSHExecutor,
    judge: Judge,
    reason: str = "",
) -> list[dict]:
    """Run a ping-sweep (no port scan) over *subnet* using Nmap.

    Uses ``nmap -sn`` (host discovery only — no port probing).
    Requires tier-1 approval because it actively probes the network.

    Returns a list of host dicts: ip, mac, mac_vendor, hostname, status.
    """
    cmd = f"sudo nmap -sn {shlex.quote(subnet)} -oX -"
    if not judge.approve("scan_lan", cmd, reason=reason):
        return []

    result = executor.run(cmd, timeout=60)
    if result["returncode"] != 0:
        stderr = result.get("stderr", "").strip()
        return [{"error": f"nmap failed: {stderr}"}]

    return _parse_nmap_xml(result["stdout"])
