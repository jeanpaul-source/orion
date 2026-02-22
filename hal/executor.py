"""SSH executor — run commands on the lab server with tiered approval."""
import subprocess

TIERS = {
    0: "read-only",
    1: "service restart",
    2: "config change",
    3: "destructive",
}

# Commands that get auto-elevated to a higher tier
TIER_RULES: list[tuple[int, list[str]]] = [
    (3, ["rm -rf", "drop table", "mkfs", "dd if="]),
    (2, ["docker run", "systemctl enable", "chmod 777", "ufw"]),
    (1, ["docker restart", "docker stop", "docker start", "systemctl restart", "systemctl stop"]),
]


def classify(command: str) -> int:
    lower = command.lower()
    for tier, patterns in TIER_RULES:
        if any(p in lower for p in patterns):
            return tier
    return 0


class SSHExecutor:
    def __init__(self, host: str, user: str):
        self.host = host
        self.user = user

    def run(self, command: str, tier: int | None = None, reason: str = "") -> dict:
        effective_tier = tier if tier is not None else classify(command)

        if effective_tier > 0:
            approved = self._request_approval(command, effective_tier, reason)
            if not approved:
                return {"approved": False, "returncode": None, "stdout": "", "stderr": ""}

        result = subprocess.run(
            ["ssh", f"{self.user}@{self.host}", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "approved": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _request_approval(self, command: str, tier: int, reason: str) -> bool:
        print(f"\n  [tier {tier} — {TIERS[tier]}]")
        if reason:
            print(f"  reason : {reason}")
        print(f"  command: {command}")
        try:
            answer = input("  approve? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            answer = "n"
        return answer == "y"
