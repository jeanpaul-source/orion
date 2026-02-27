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
