"""Unit tests for hal/judge.py — classify_command() and tier_for().

These tests require no external services (no Ollama, no SSH, no Prometheus).
They verify the policy gate logic that controls what HAL is allowed to do
on the server. A silent regression here could auto-approve a destructive command.

Run with: pytest tests/test_judge.py -v
"""

import pytest

from hal.judge import classify_command, tier_for

# ---------------------------------------------------------------------------
# classify_command — safe read-only commands → tier 0
# ---------------------------------------------------------------------------

SAFE_TIER_0 = [
    "ps aux",
    "ps -ef",
    "df -h",
    "df -h /docker",
    "free -m",
    "uptime",
    "cat /etc/os-release",
    "head -n 50 /var/log/syslog",
    "tail -f /var/log/nginx/access.log",
    "ls -la /opt/homelab-infrastructure",
    "grep -r 'prometheus' /opt/homelab-infrastructure",
    "journalctl -u prometheus --since today",
    "journalctl --user -u vllm -n 100",
    "netstat -tlnp",
    "ss -tlnp",
    "ip addr show",
    "hostname",
    "uname -r",
    "id",
    "whoami",
    "date",
    "find /opt -name '*.yml'",
    "echo hello",
    "wc -l /opt/homelab-infrastructure/monitoring-stack/docker-compose.yml",
    "stat /opt/homelab-infrastructure",
    "lscpu",
    "lsblk",
    "lsof -i :9091",
    "ping -c 3 192.168.5.10",
    # F1 additions — common diagnostic commands
    "du -sh /opt",
    "du -h --max-depth=1 /var/log",
    "nvidia-smi",
    "nvidia-smi --query-gpu=memory.used --format=csv",
    "sensors",
    "lsmod",
    "which python3",
    "file /usr/bin/python3",
    "timedatectl",
    "hostnamectl",
    "nproc",
    "getconf NPROCESSORS_ONLN",
    "dig example.com",
    "nslookup example.com",
    "nmcli device status",
    "resolvectl status",
    "last -n 10",
    "w",
    "who",
    "dmesg",
    "awk '{print $1}' /etc/os-release",
    "cut -d: -f1 /etc/os-release",
    "diff /etc/os-release /etc/os-release",
    "dpkg-query -l",
    "rpm -qa",
    "realpath /usr/bin/python3",
    "readlink /usr/bin/python3",
    "md5sum /etc/os-release",
    "traceroute example.com",
]


@pytest.mark.parametrize("cmd", SAFE_TIER_0)
def test_safe_commands_are_tier_0(cmd):
    """Read-only inspection commands must never require approval."""
    tier = classify_command(cmd)
    assert tier == 0, (
        f"'{cmd}' classified as tier {tier}, expected 0. "
        "If this command is genuinely safe, add its first token to _SAFE_FIRST_TOKENS "
        "or its (first, second) pair to _SAFE_COMPOUND in hal/judge.py."
    )


# ---------------------------------------------------------------------------
# classify_command — compound safe tokens → tier 0
# ---------------------------------------------------------------------------

SAFE_COMPOUND_TIER_0 = [
    "systemctl status prometheus",
    "systemctl status ollama",
    "docker ps",
    "docker ps -a",
    "docker stats",
    "docker logs grafana",
    "docker inspect pgvector",
    "docker images",
    "docker network ls",
    # F1 additions — systemctl read-only subcommands
    "systemctl show prometheus",
    "systemctl is-active ollama",
    "systemctl is-enabled vllm",
    "systemctl is-failed harvest.service",
    "systemctl list-units --type=service",
    "systemctl list-timers",
    "systemctl list-timers harvest.timer",
    "systemctl list-sockets",
    "systemctl list-dependencies prometheus",
    "systemctl cat vllm.service",
    # F1 additions — docker read-only subcommands
    "docker top pgvector",
    "docker port grafana",
    "docker info",
    "docker version",
    "docker df",
    "docker compose ps",
    "docker compose logs prometheus",
    # F1 additions — ip subcommands
    "ip addr",
    "ip address show",
    "ip route",
    "ip route show",
    "ip link show",
    "ip neigh",
    "ip rule list",
    # F1 additions — package manager queries
    "dnf list installed",
    "dnf info python3",
    "dnf search ollama",
    "dnf repoquery --installed python3",
    "apt list --installed",
    "apt show python3",
    "apt search ollama",
]


@pytest.mark.parametrize("cmd", SAFE_COMPOUND_TIER_0)
def test_compound_safe_commands_are_tier_0(cmd):
    """Compound safe commands (e.g. 'docker ps', 'systemctl status') must be tier 0."""
    tier = classify_command(cmd)
    assert tier == 0, f"'{cmd}' → tier {tier}, expected 0"


# ---------------------------------------------------------------------------
# classify_command — service control → tier 1
# ---------------------------------------------------------------------------

TIER_1_COMMANDS = [
    "systemctl restart prometheus",
    "systemctl restart ollama",
    "systemctl stop grafana",
    "systemctl start node-exporter",
    "docker restart pgvector",
    "docker stop nginx",
    "docker start agent-zero",
]


@pytest.mark.parametrize("cmd", TIER_1_COMMANDS)
def test_service_control_is_tier_1(cmd):
    """Service restart/stop/start must require user approval (tier 1)."""
    tier = classify_command(cmd)
    assert tier == 1, f"'{cmd}' → tier {tier}, expected 1"


# ---------------------------------------------------------------------------
# classify_command — config changes → tier 2
# ---------------------------------------------------------------------------

TIER_2_COMMANDS = [
    "docker run -d nginx",
    "systemctl enable myservice",
    "systemctl disable prometheus",
    "chmod 777 /opt/homelab-infrastructure",
    "ufw allow 8080",
    "echo 'something' > /etc/sysctl.conf",
]


@pytest.mark.parametrize("cmd", TIER_2_COMMANDS)
def test_config_changes_are_tier_2(cmd):
    """Config-change commands must require explicit approval with explanation (tier 2)."""
    tier = classify_command(cmd)
    assert tier == 2, f"'{cmd}' → tier {tier}, expected 2"


# ---------------------------------------------------------------------------
# classify_command — destructive patterns → tier 3
# ---------------------------------------------------------------------------

TIER_3_COMMANDS = [
    "rm -rf /opt/homelab-infrastructure",
    "rm -rf /",
    "drop table documents",
    "DROP TABLE documents;",
    "mkfs.ext4 /dev/sdb",
    "dd if=/dev/zero of=/dev/sda",
    ":(){:|:&};:",
]


@pytest.mark.parametrize("cmd", TIER_3_COMMANDS)
def test_destructive_commands_are_tier_3(cmd):
    """Destructive commands must require explicit confirmation (tier 3)."""
    tier = classify_command(cmd)
    assert tier == 3, f"'{cmd}' → tier {tier}, expected 3"


# ---------------------------------------------------------------------------
# classify_command — sensitive paths bump unknown commands to tier 1
# ---------------------------------------------------------------------------

SENSITIVE_PATH_COMMANDS = [
    "cat /run/homelab-secrets/pgvector-kb.env",
    "ls ~/.ssh",
    "cat /etc/shadow",
    "cat /etc/passwd",
    "wc -l /etc/passwd",
    "stat /root/somefile",
    "nano .env",
]


@pytest.mark.parametrize("cmd", SENSITIVE_PATH_COMMANDS)
def test_sensitive_path_commands_are_at_least_tier_1(cmd):
    """Commands touching sensitive paths must require approval (tier >= 1)."""
    tier = classify_command(cmd)
    assert tier >= 1, f"'{cmd}' → tier {tier}, expected >= 1"


# ---------------------------------------------------------------------------
# tier_for — non-command action types
# ---------------------------------------------------------------------------


def test_tier_for_search_kb():
    assert tier_for("search_kb") == 0


def test_tier_for_get_metrics():
    assert tier_for("get_metrics") == 0


def test_tier_for_remember_fact():
    assert tier_for("remember_fact") == 0


def test_tier_for_write_file():
    # Non-repo, non-sensitive path → tier 2 (config change)
    assert tier_for("write_file", "/tmp/test.txt") == 2


def test_tier_for_write_file_repo_path():
    # Writing to repo → tier 3 (policy: propose only, never apply)
    assert tier_for("write_file", "hal/agent.py") == 3


def test_tier_for_write_file_sensitive_path():
    # Writing to sensitive path → tier 3 (destructive)
    assert tier_for("write_file", "/etc/shadow") == 3


def test_tier_for_read_file_normal():
    assert tier_for("read_file", "/opt/homelab-infrastructure/something.yml") == 0


def test_tier_for_read_file_sensitive():
    assert tier_for("read_file", "/run/homelab-secrets/pgvector-kb.env") == 1


def test_tier_for_list_dir_normal():
    assert tier_for("list_dir", "/opt/homelab-infrastructure") == 0


def test_tier_for_list_dir_sensitive():
    assert tier_for("list_dir", "~/.ssh") == 1


def test_tier_for_unknown_action():
    # Unknown action types default to tier 2 (default-deny: explain + approve)
    assert tier_for("some_unknown_action") == 2


# ---------------------------------------------------------------------------
# Judge.record_outcome — audit log outcome entries
# ---------------------------------------------------------------------------


def test_record_outcome_writes_success_entry(tmp_path):
    """record_outcome appends a JSON outcome entry with status='outcome'."""
    import json

    from hal.judge import Judge

    log = tmp_path / "audit.log"
    judge = Judge(audit_log=log)
    judge.record_outcome("run_command", "ps aux", "success")

    lines = log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["status"] == "outcome"
    assert entry["outcome"] == "success"
    assert entry["action"] == "run_command"
    assert entry["detail"] == "ps aux"


def test_record_outcome_writes_error_entry(tmp_path):
    """record_outcome records error outcomes correctly."""
    import json

    from hal.judge import Judge

    log = tmp_path / "audit.log"
    judge = Judge(audit_log=log)
    judge.record_outcome("run_command", "some_cmd", "error")

    entry = json.loads(log.read_text().splitlines()[0])
    assert entry["outcome"] == "error"
    assert entry["status"] == "outcome"


def test_record_outcome_truncates_long_detail(tmp_path):
    """detail is capped at 500 chars to match _log() behaviour."""
    import json

    from hal.judge import Judge

    log = tmp_path / "audit.log"
    judge = Judge(audit_log=log)
    long_detail = "x" * 600
    judge.record_outcome("search_kb", long_detail, "success")

    entry = json.loads(log.read_text().splitlines()[0])
    assert len(entry["detail"]) == 500


# ---------------------------------------------------------------------------
# Trust evolution — _trust_key, _load_trust_overrides, approve() integration
# ---------------------------------------------------------------------------


def test_trust_key_run_command_uses_first_token():
    """run_command keys group by first token so 'ps aux' and 'ps -ef' share a bucket."""
    from hal.judge import _trust_key

    assert _trust_key("run_command", "ps aux") == "run_command:ps"
    assert _trust_key("run_command", "ps -ef") == "run_command:ps"
    assert (
        _trust_key("run_command", "systemctl restart grafana")
        == "run_command:systemctl"
    )


def test_trust_key_non_command_is_action_type():
    """Non-run_command actions use their action type as the key."""
    from hal.judge import _trust_key

    assert _trust_key("search_kb", "some query") == "search_kb"
    assert _trust_key("get_metrics", "") == "get_metrics"


def test_load_trust_overrides_promotes_after_threshold(tmp_path):
    """An action with >= 10 outcomes and >= 90% success rate earns an override."""
    import json

    from hal.judge import _TRUST_MIN_SAMPLES, _load_trust_overrides

    log = tmp_path / "audit.log"
    # Write 10 successful outcomes for run_command:systemctl
    # why: minimum samples exactly at threshold should trigger promotion.
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
        for _ in range(_TRUST_MIN_SAMPLES)
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    assert "run_command:systemctl" in overrides
    assert overrides["run_command:systemctl"] == 0
    assert len(demotions) == 0


def test_load_trust_overrides_requires_min_samples(tmp_path):
    """Fewer than _TRUST_MIN_SAMPLES outcomes must not trigger promotion."""
    import json

    from hal.judge import _TRUST_MIN_SAMPLES, _load_trust_overrides

    log = tmp_path / "audit.log"
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
        for _ in range(_TRUST_MIN_SAMPLES - 1)
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    assert "run_command:systemctl" not in overrides


def test_load_trust_overrides_requires_success_rate(tmp_path):
    """A success rate below the threshold must not trigger promotion."""
    import json

    from hal.judge import _load_trust_overrides

    log = tmp_path / "audit.log"
    # 8 successes + 2 errors = 80% success rate — below the 90% threshold.
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
    ] * 8 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
    ] * 2
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    assert "run_command:systemctl" not in overrides


def test_load_trust_overrides_ignores_approval_entries(tmp_path):
    """Only status='outcome' entries count — approval entries are ignored."""
    import json

    from hal.judge import _TRUST_MIN_SAMPLES, _load_trust_overrides

    log = tmp_path / "audit.log"
    # Mix of approval and outcome entries; only outcomes should count.
    entries = [
        {
            "status": "auto",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
    ] * 20 + [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
    ] * (_TRUST_MIN_SAMPLES - 1)
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    # why: approval entries must not inflate the outcome count.
    assert "run_command:systemctl" not in overrides


def test_approve_applies_trust_override_for_tier1(tmp_path):
    """approve() reduces tier 1 → 0 when trust override exists for the action key."""
    import json

    from hal.judge import _TRUST_MIN_SAMPLES, Judge

    log = tmp_path / "audit.log"
    # Pre-populate audit log with enough successful outcomes.
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl status grafana",
        }
        for _ in range(_TRUST_MIN_SAMPLES)
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    judge = Judge(audit_log=log)
    # systemctl commands are tier 1 statically; trust override should make it tier 0.
    # why: the full approve() path must be exercised to confirm overrides are applied.
    result = judge.approve("run_command", "systemctl status grafana")
    assert result is True  # auto-approved via trust evolution, no prompt needed

    # The audit log entry should record tier 0 (not tier 1).
    outcome_entries = [json.loads(line) for line in log.read_text().splitlines()]
    approval_entry = outcome_entries[-1]  # last entry is the approval log
    assert approval_entry["tier"] == 0


# Trust demotion (C5)
# ---------------------------------------------------------------------------


def test_load_trust_overrides_demotes_below_demotion_rate(tmp_path):
    """A key with ≥10 samples and success rate < 70% appears in demotions."""
    import json

    from hal.judge import _load_trust_overrides

    log = tmp_path / "audit.log"
    # 6 successes + 4 failures = 60% — below the 70% demotion threshold.
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 6 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 4
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    assert "run_command:systemctl" not in overrides
    assert "run_command:systemctl" in demotions


def test_load_trust_overrides_demotion_writes_audit_entry(tmp_path):
    """Demotion writes a 'trust_demotion' entry to the audit log (once)."""
    import json

    from hal.judge import _load_trust_overrides

    log = tmp_path / "audit.log"
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 6 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 4
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    _load_trust_overrides(log)

    # The audit log should now contain a trust_demotion entry.
    lines = log.read_text().strip().splitlines()
    demotion_entries = [json.loads(ln) for ln in lines if "trust_demotion" in ln]
    assert len(demotion_entries) == 1
    assert demotion_entries[0]["status"] == "trust_demotion"
    assert demotion_entries[0]["action"] == "run_command"

    # Calling again should not add a duplicate demotion entry.
    _load_trust_overrides(log)
    lines2 = log.read_text().strip().splitlines()
    demotion_entries2 = [json.loads(ln) for ln in lines2 if "trust_demotion" in ln]
    assert len(demotion_entries2) == 1


def test_load_trust_overrides_no_demotion_between_70_and_90(tmp_path):
    """Rate between 70-89% is neither promoted nor demoted — stays at static tier."""
    import json

    from hal.judge import _load_trust_overrides

    log = tmp_path / "audit.log"
    # 8 successes + 2 failures = 80% — above demotion (70%), below promotion (90%).
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 8 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 2
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    overrides, demotions = _load_trust_overrides(log)
    assert "run_command:systemctl" not in overrides
    assert "run_command:systemctl" not in demotions


def test_demoted_key_blocks_future_promotion(tmp_path):
    """A key that was demoted should not be promoted even if cumulative rate recovers."""
    import json

    from hal.judge import _load_trust_overrides

    log = tmp_path / "audit.log"
    # Phase 1: 6 successes + 4 failures = 60% → triggers demotion
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 6 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 4
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    # First load triggers demotion
    overrides1, demotions1 = _load_trust_overrides(log)
    assert "run_command:systemctl" in demotions1

    # Phase 2: Add 20 more successes → cumulative = 26/30 = 86.7% (still below 90%)
    # but let's add enough to push to 92%+: need 36 success total → 30 more
    more_entries = [
        json.dumps(
            {
                "status": "outcome",
                "outcome": "success",
                "action": "run_command",
                "detail": "systemctl restart grafana",
            }
        )
        for _ in range(30)
    ]
    with open(log, "a") as f:
        f.write("\n".join(more_entries) + "\n")

    # Second load: cumulative = 36/40 = 90% but demotion entry blocks promotion
    overrides2, demotions2 = _load_trust_overrides(log)
    assert "run_command:systemctl" not in overrides2
    assert "run_command:systemctl" in demotions2


def test_approve_respects_demotion_flag(tmp_path, monkeypatch):
    """approve() should not apply trust promotion for demoted keys."""
    import json

    from hal.judge import Judge, _load_trust_overrides

    log = tmp_path / "audit.log"
    # Phase 1: 6 successes + 4 failures = 60% → triggers demotion
    entries = [
        {
            "status": "outcome",
            "outcome": "success",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 6 + [
        {
            "status": "outcome",
            "outcome": "error",
            "action": "run_command",
            "detail": "systemctl restart grafana",
        }
    ] * 4
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    # Trigger demotion — writes trust_demotion entry to log
    _load_trust_overrides(log)

    # Phase 2: Add 30 more successes → cumulative = 36/40 = 90%
    more_entries = [
        json.dumps(
            {
                "status": "outcome",
                "outcome": "success",
                "action": "run_command",
                "detail": "systemctl restart grafana",
            }
        )
        for _ in range(30)
    ]
    with open(log, "a") as f:
        f.write("\n".join(more_entries) + "\n")

    # Deny when prompted — if trust demotion works, we get prompted (tier 1 stays)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    # Now create judge — it should see the demotion entry and refuse promotion
    judge = Judge(audit_log=log)
    # This is tier 1 (systemctl restart) — should NOT be promoted due to demotion
    result = judge.approve("run_command", "systemctl restart grafana")
    # Tier 1 requires prompt → denied because we answered "n"
    assert result is False
