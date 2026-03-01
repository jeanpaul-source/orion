# Plan: Architectural Backlog — Lab-Specific Hardcodings

Created: 2026-03-01
Status: Items 3 and 4 complete; Items 1 and 2 remain (not yet started)

---

## Verified State

The ROADMAP.md "Architectural backlog" section documents "five lab-specific hardcodings that
prevent ORION from deploying on a second machine without source edits." It then lists four
numbered items. No fifth item is explicitly documented; the count is off. Verified against
actual code on 2026-03-01.

---

### Item 1 — System prompt hardcodes lab details

File: hal/bootstrap.py, function get_system_prompt()

The system prompt contains these literal strings (verified line by line):
  - "the-lab (192.168.5.10)" — hostname and IP in the LAB HOST section header
  - "Intel Core Ultra 7 265K (20 cores)" — CPU model
  - "62 GB DDR5" — RAM
  - "RTX 3090 Ti (24 GB VRAM)" — GPU
  - "Samsung 990 PRO 2TB (/)" — storage
  - "2x WD SN850X 2TB (/docker, /data/projects)" — storage
  - Exact ports: ":8000", ":11434", ":9091", ":3001", ":9092", ":5432", ":9090", ":3000"
  - "/opt/homelab-infrastructure/monitoring-stack/"
  - "/var/log/falco/events.json"
  - "Osquery 5.21.0" — version number
  - "Nmap 7.92" — version number
  - "enp130s0" — network interface name
  - Specific mount points: "/docker", "/data/projects"
  - "~/.orion/watchdog_state.json", "~/.orion/watchdog.log", "~/.orion/harvest_last_run"

All of these would be wrong on any machine other than the-lab.

The Config dataclass (hal/config.py) has: ollama_host, vllm_url, prometheus_url, lab_host,
lab_user, ntopng_url, ntfy_url — but NOT hardware specs, service paths, mount points,
interface name, or version numbers.

Relationship to config.py: some prompt values (lab_host IP, service ports) could be derived
from existing Config fields. Others (hardware specs, file paths) are not in Config at all and
would need to be added or templated separately.

---

### Item 2 — Judge policy rules hardcoded in Python source

File: hal/judge.py

_CMD_RULES (lines ~32-98): list of (tier, [patterns]) tuples for 3-tier, 2-tier, and 1-tier
shell patterns. These are Python list literals. No way to extend per-deployment without editing
source.

_SENSITIVE_PATHS (lines ~100-113): list of absolute path strings. The entry
os.path.expanduser("~/.ssh") is relativized at import time; the others are absolute literals
like "/run/homelab-secrets", "/etc/shadow", "/etc/sudoers", etc.

_SENSITIVE_BASENAMES (lines ~115-120): frozenset with ".env" only.

_SAFE_FIRST_TOKENS (lines ~122-172): frozenset of safe read-only command first tokens.
ps, top, htop, df, ls, cat, head, tail, grep, wc, sort, uniq, echo, uname, hostname,
journalctl, etc.

_SAFE_COMPOUND (lines ~174-183): frozenset of two-token safe prefixes.
(systemctl, status), (docker, ps), (docker, stats), (docker, logs), (docker, inspect),
(docker, images), (docker, network).

_ACTION_TIERS (lines ~185-210): dict mapping tool names to tier numbers.

_GIT_WRITE_SUBCOMMANDS and _GIT_SAFE_SUBCOMMANDS (lines ~270-315): frozensets of git
subcommand classifications.

All of these are in Python source. Adding a site-specific safe command (e.g., a homelab tool
specific to machine 2) requires editing judge.py, which is shared policy code.

The ROADMAP item says "move them to hal/judge_rules.py or a config section." Whether this
means a YAML/TOML file, a separate Python module that's imported, or a new Config section is
not specified.

---

### Item 3 — config.py has hardcoded defaults for lab-specific values

File: hal/config.py

lab_host=os.getenv("LAB_HOST", "192.168.5.10")  — line 42
lab_user=os.getenv("LAB_USER", "jp")            — line 43

These are the silent fallbacks when LAB_HOST and LAB_USER are not in .env. On any machine
other than the-lab these defaults silently connect to the wrong machine.

For comparison, OLLAMA_HOST, PGVECTOR_DSN, and PROMETHEUS_URL all call _required_env() which
raises RuntimeError("... must be set in .env") if missing. LAB_HOST and LAB_USER do not.

The ROADMAP says "if .env is missing, fail loudly rather than silently connecting to a
different machine's IP." The fix is to make LAB_HOST and LAB_USER required via _required_env(),
or at minimum document in the comment that these fallbacks are wrong for any other deployment.

Other defaults in config.py:
  chat_model=os.getenv("CHAT_MODEL", "Qwen/Qwen2.5-32B-Instruct-AWQ") -- acceptable default
  embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text:latest") -- acceptable default
  vllm_url=os.getenv("VLLM_URL", "http://localhost:8000") -- localhost, acceptable
  ntopng_url=os.getenv("NTOPNG_URL", "http://localhost:3000") -- localhost, acceptable
  ntfy_url, telegram_bot_token, tavily_api_key -- empty string disables, acceptable

Only lab_host (192.168.5.10) and lab_user (jp) are wrong-by-default for other machines.

---

### Item 4 — Harvest collectors are hardcoded to this lab's layout

File: harvest/collect.py

Exact hardcodings verified:
  - Line 211: "curl -s http://localhost:11434/api/tags" — hardcodes Ollama URL
  - Line 238: f"Lab hardware: the-lab (192.168.5.10)" — hardcoded in doc content
  - Lines 265-268: Path("/opt/homelab-infrastructure") — base path for config files
  - Lines 270-276: specific compose file list:
      "monitoring-stack/docker-compose.yml"
      "monitoring-stack/prometheus.yml"
      "pgvector-kb/docker-compose.yml"
      "agent-zero/docker-compose.yml"  ← agent-zero does not exist (D1 in SESSION_FINDINGS)
  - Line 348: _STATIC_DOCS_ROOT = Path("/data/orion/orion-data/documents/raw") — absolute path
  - collect_systemd_units() hardcodes: ["ollama.service", "pgvector-kb-api.service"]
  - collect_hardware() hardcodes Ollama query to localhost:11434

The ROADMAP says "abstract the interface so collectors can register by name and fail gracefully
if the underlying tool is absent." The current collect_all() list is hardcoded; collectors that
fail raise exceptions that are caught and logged but there is no graceful degradation per-collector.

Note: collect_docker_containers() uses subprocess.run(["docker", ...]) with a parameter
list — no shell=True injection risk. collect_system_state() uses _run(cmd) which is shell=True
but for known-safe commands. These are not security issues but they do assume Docker and
specific commands are present.

---

### Item 5 — Not explicitly documented in ROADMAP

The ROADMAP section header says "five hardcodings" but the numbered list has only four items.
No fifth item is documented.

From code inspection, a candidate fifth hardcoding:
  - hal/server.py: the port (8087) is hardcoded as the default in the CLI arg parser. The
    tasks.json also hardcodes --port 8087. However, this is easy to override via CLI arg and
    is not truly "preventing deployment on a second machine."

Other candidates:
  - The watchdog thresholds in hal/watchdog.py are numeric literals (CPU >=85%, etc.) but
    these are documented in the system prompt and could reasonably be in Config.
  - The system prompt mentions specific mount points (/docker, /data/projects) not in Config.

The factual answer: ROADMAP says five but documents four. If a fresh context window finds a
genuine fifth hardcoding during implementation, it should document it as an additional finding.
Do not treat the ROADMAP count as authoritative.

---

## Problem Statement

ORION's architecture is cleanly generic but the implementation has at least four (possibly more)
places where lab-specific values are embedded in source code. A second deployment means editing
hal/bootstrap.py, hal/judge.py, hal/config.py, and harvest/collect.py rather than adjusting
configuration. The goal is to push all deployment-specific values to .env and .env.example, with
the codebase containing only structure — not values.

This is a portability and maintainability problem. It also creates maintenance risk: if the
server's hardware or service layout changes, every piece of hardcoded documentation in the
system prompt becomes wrong silently.

---

## Relevant Code Locations

Item 1 (system prompt):
- hal/bootstrap.py get_system_prompt(): the full function, lines ~38–170
- hal/config.py Config dataclass: existing fields to understand what is already configurable
- hal/config.py load(): to understand what env vars are already read
- .env.example: to understand what operators are expected to configure

Item 2 (Judge rules):
- hal/judge.py: _CMD_RULES, _SENSITIVE_PATHS, _SENSITIVE_BASENAMES, _SAFE_FIRST_TOKENS,
  _SAFE_COMPOUND, _ACTION_TIERS, _GIT_WRITE_SUBCOMMANDS, _GIT_SAFE_SUBCOMMANDS
  (approximately lines 32–210, 265–315)
- hal/judge.py classify_command(), tier_for(): these consume the above data structures
- tests/test_judge.py and tests/test_judge_hardening.py: comprehensive coverage of judge
  behavior; any structural change requires careful test review

Item 3 (config defaults):
- hal/config.py lines 42-43: lab_host and lab_user defaults
- hal/config.py _required_env(): the existing pattern for required values
- .env.example: add LAB_HOST and LAB_USER if making them required

Item 4 (harvest collectors):
- harvest/collect.py: entire file
- harvest/collect.py collect_all(): the hardcoded collector list
- harvest/main.py: how collect_all() is called
- tests/test_harvest.py: coverage of harvest pipeline

---

## Constraints

**Item 1 (system prompt):**
- The system prompt is currently one large f-string in get_system_prompt(). Any refactor must
  produce identical or improved prompt quality — this is the primary driver of LLM behavior.
- Hardware specs (CPU, RAM, GPU) cannot be read from .env easily; they'd need to come from the
  KB (which is harvested from the actual server) or from a separate config section.
- Port numbers already exist in Config fields (prometheus_url, vllm_url contain the ports).
  Deriving ports from URLs is feasible but adds coupling.
- If the system prompt becomes a template, the test suite may need updates for any tests that
  mock or inspect prompt content. Check tests/test_agent_loop.py and tests/test_server.py.

**Item 2 (Judge rules):**
- The Judge is the security boundary. Externalizing rules to a YAML file means the file must
  be loaded at startup and validated. A malformed or missing rules file must fail loud, not
  silently apply no rules — that would be an auto-approve default, which is worse than the
  current hardcoding.
- Tests in tests/test_judge.py and tests/test_judge_hardening.py test specific command strings
  against expected tiers. If the rules move to an external file, the tests must either load
  that file or be rewritten to test the loader + behavior together.
- The git write blocking (_GIT_WRITE_SUBCOMMANDS) and path canonicalization (_is_repo_path)
  are structural policy that probably should remain in code even if other rules move out.

**Item 3 (config defaults):**
- Making lab_host and lab_user required (via _required_env) will break any invocation that
  doesn't have a .env file — including local dev on a laptop without these vars set.
- This is the direct trade-off the ROADMAP proposes: fail loudly vs. silently wrong. Assess
  whether existing CI/CD and dev setup instructions handle this.
- Tests that instantiate Config directly (tests/test_config.py) will need to set LAB_HOST
  and LAB_USER in the test environment if these become required.

**Item 4 (harvest collectors):**
- collect_all() is called by harvest/main.py. Failures in individual collectors are caught
  with a WARNING print. The current behavior is already somewhat graceful (per-collector
  try/except in collect_all). The ask is to make this more formal.
- The hardcoded Ollama URL in collect_system_state() (localhost:11434) conflicts with the
  already-configurable OLLAMA_HOST in Config. These should be consistent.
- The agent-zero path in collect_config_files() references a service that does not exist on
  the server (D1 in SESSION_FINDINGS). This currently silently produces no docs but it is
  dead config that should be removed.
- tests/test_harvest.py: verify coverage before changing collectors.

---

## Open Questions

**Item 1 (system prompt):**
1. How much of the hardware spec should stay in the prompt vs. be sourced from the KB? The KB
   already has lab hardware docs from collect_hardware(). The prompt could be shorter and point
   the LLM to "use search_kb for hardware specs" rather than listing them inline.
2. Should get_system_prompt() accept a Config parameter so ports/hostnames are derived from
   Config fields, or should a separate "lab profile" concept be introduced?
3. If the hardware section is removed from the prompt and sourced from KB, what is the
   acceptable latency impact on queries that need that data?

**Item 2 (Judge rules):**
1. YAML file vs. separate Python module vs. Config section — which externalization approach?
   YAML makes the rules editable without touching Python; a separate Python module keeps type
   safety; a Config section keeps everything in .env. These have very different implementation
   complexity.
2. Should all rule structures be externalizable, or only the site-specific ones like
   _SENSITIVE_PATHS and a site-specific safe command whitelist? The git blocking and
   _EVASION_PATTERNS are universal security policy that probably should not be per-deployment.

**Item 3 (config defaults):**
1. Make lab_host and lab_user hard-required (RuntimeError if not set) — or soft-required
   (log a warning, proceed)? The ROADMAP says "fail loudly."
2. Does the .env.example already have LAB_HOST and LAB_USER? Verify before implementation.

**Item 4 (harvest collectors):**
1. "Pluggable collectors" could mean many things: a function registry, a list of YAML-declared
   shell commands, a base class with subclasses. What level of abstraction is appropriate?
2. The Ollama URL in collect_system_state() should probably come from Config.ollama_host
   rather than hardcoded localhost. Is that the intent?
3. Should the agent-zero path in collect_config_files() be deleted outright, or replaced with
   a mechanism to list config paths from .env?

---

## Suggested Sequence

These items are largely independent. Suggested order by blast radius:

1. Item 3 (config defaults) — smallest change, clear behavior, well-covered by tests.
   Change lab_host and lab_user to use _required_env; update .env.example; update
   tests/test_config.py. One commit.

2. Item 4, partial (agent-zero path removal + Ollama URL from Config) — remove the dead
   agent-zero path from collect_config_files(), make Ollama URL come from an argument
   rather than hardcoded localhost. Small, low-risk. One or two commits.

3. Item 4, full (pluggable collectors) — design and implement the abstraction. This is the
   most open-ended item; get operator input on approach before starting.

4. Item 1 (system prompt) — requires the most judgment about what to template vs. what to
   keep inline. Propose the template design before implementing; test carefully that prompt
   quality is not degraded.

5. Item 2 (Judge rules) — highest existing test coverage, most security-sensitive. Do last.
   The current hardcoding is not wrong, just inflexible. Get operator input on the
   externalization approach before touching the Judge.

Do not implement Items 1 and 2 in the same branch or session. They are independent and
should be individually reviewable.

---

## Pending follow-up (post-implementation)

`/run/homelab-secrets` still appears in `_SENSITIVE_PATHS` in `hal/judge.py`. It is the
only site-specific entry in an otherwise universal list. Now that `JUDGE_EXTRA_SENSITIVE_PATHS`
exists, the correct state is:

1. Add `JUDGE_EXTRA_SENSITIVE_PATHS=/run/homelab-secrets` to the server's `.env`
2. Remove `/run/homelab-secrets` from `_SENSITIVE_PATHS` in `hal/judge.py`
3. One commit — `fix(judge): move /run/homelab-secrets to .env`

Do not do step 2 before step 1 is confirmed on the server. The path remains protected during
the transition because it is still in `_SENSITIVE_PATHS` until removed.
