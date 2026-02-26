# HAL Internet Access — Planning Document

*Created: Feb 25, 2026*

## 1. Taxonomy of Internet Access Types

### Level 0 — Read-Only Web Search (API-based)

**What HAL can do:** Send a text query to a search API, receive titles + snippets + URLs.
No page content is fetched — only search index results.

**Homelab examples:**
- "What kernel version fixes the XFS corruption bug on 6.x?"
- "Is there a known Falco false positive for systemd-userwork?"
- "What's the latest vLLM release?"

**New files:** `hal/web.py`, tool entry in `hal/agent.py` TOOLS + `_dispatch`

**Judge tier: 0** — read-only, no side effects. The query text is the privacy surface:
if HAL searches "my lab at 192.168.5.10 has a vulnerability in…" it leaks topology.
Mitigation: tool description instructs the LLM to formulate generic queries; Judge logs
every outbound query for audit.

**Privacy/security tradeoffs:**
- Search queries are sent to a third-party API. The query itself is the leak vector.
- No credentials, cookies, or lab IPs transmitted (unless the LLM puts them in the query).
- Low risk if tool description says "never include IP addresses, hostnames, or internal
  paths in search queries."

**API keys / cost (2026):**

| Backend | Key required | Free tier | Notes |
|---------|-------------|-----------|-------|
| DuckDuckGo Instant Answer | No | Free, no key | Limited: instant answers only, not full search. No official search API. |
| Brave Search API | Yes | 2,000 queries/mo | Best privacy stance among commercial APIs. |
| Tavily | Yes | 1,000 queries/mo | Purpose-built for AI agents. Returns pre-extracted content. |
| SearXNG (self-hosted) | No | Unlimited | Metasearch engine. Full control, zero leak. Requires running a container. |


### Level 1 — Web Page Fetching (Read-Only Content Extraction)

**What HAL can do:** Fetch a URL, extract article text (strip nav/ads/scripts), return
clean text. This is what `harvest/parsers.py` already does with trafilatura — but at
query time instead of harvest time.

**Homelab examples:**
- "Read the release notes at https://github.com/vllm-project/vllm/releases/tag/v0.7.0"
- "What does this Stack Overflow answer say?"
- "Fetch the official Falco docs on rule tuning"

**New files:** `hal/web.py` — `fetch_url()` using trafilatura (already a dependency)

**Judge tier: 1** — no state change, but server makes outbound HTTP request to arbitrary URL.
Tier 1 because:
- URL is user-controlled or LLM-generated — could be malicious
- SSRF risk: LLM could request `http://localhost:8000/` or `http://192.168.5.10:5432/`
- DNS rebinding, redirect chains

**Mitigations needed in Judge:**
- URL allowlist/blocklist: block RFC1918, link-local, localhost, `.local` domains
- Block non-HTTP(S) schemes (`file://`, `ftp://`, `gopher://`)
- Follow redirects but re-validate final URL against blocklist
- Timeout (10s hard cap), response size cap (1MB)

**Cost:** Zero — `requests` + `trafilatura` already installed.


### Level 2 — External API Reads (Structured Data)

**What HAL can do:** Query pre-configured external APIs that return structured data.

**Homelab examples:**
- GitHub API: "What are the open issues on vllm-project/vllm?"
- Docker Hub API: "What's the latest tag for `prom/prometheus`?"
- CVE databases: "Are there known CVEs for Ollama 0.5.x?"

**Judge tier: 0 for read-only public APIs; tier 1 for authenticated APIs** (PATs can be
misused). Principle: narrowest possible token scope. GitHub fine-grained PATs can be
scoped to specific repos, read-only.

**Cost:** All free tiers far exceed homelab usage.


### Level 3 — External API Writes

**What HAL can do:** Create/modify external resources — open GitHub issues, post comments,
send webhooks.

**Judge tier: 2 minimum** (creates persistent external state). **Tier 3 for destructive
writes** (close issue, delete release, merge PR).

**Not the starting point.** This comes after read-only web access is proven reliable.


### Level 4 — Browser Automation (Playwright/Selenium)

**Not recommended for HAL.** Complexity-to-value ratio is terrible for a homelab.
Playwright needs ~400MB Chromium, is flaky in containers, and LLM browser driving is
unreliable. Every homelab service that matters has an API or CLI.


### Level 5 — Unrestricted Outbound Network

**Never.** Violates core design principle. No Judge tier makes this safe.


---

## 2. The Right Starting Point

### What HAL currently cannot answer

Three categories of query currently fail:

1. **"What version of X is current?"** — Software releases, CVEs, changelogs. KB only
   knows what was harvested.
2. **"How do I configure X?"** — When the answer isn't in the ~727 harvested files.
3. **"Is this a known issue?"** — Bug reports, GitHub issues, forum threads.

### Recommendation: Level 0 + Level 1 combined — `web_search` + `fetch_url`

**Why both together:** Search that returns only snippets is marginally useful — the LLM
usually needs full page content. Pattern: `web_search(query)` → gets URL → `fetch_url(url)`
→ reads content → synthesizes answer. Without `fetch_url`, search returns 3-line snippets
that aren't enough.

**Why not just `fetch_url`:** Without search, the user must provide URLs. The LLM can't
discover information independently.

### Which search backend

**Recommendation: Tavily** as primary, SearXNG as long-term self-hosted option.

| Factor | Tavily | Brave Search | SearXNG |
|--------|--------|-------------|---------|
| Agent-optimized | Yes — returns extracted content | No — titles + snippets | No — titles + snippets |
| Privacy | Queries go to Tavily (privacy-focused) | Queries go to Brave | Fully self-hosted |
| Free tier | 1,000/mo | 2,000/mo | Unlimited |
| Setup effort | `pip install tavily-python` + key | HTTP API, no SDK | Docker container + config |
| Quality | High — purpose-built for LLM use | High search quality | Depends on upstream engines |

Tavily returns pre-extracted content — for simple queries, you don't need `fetch_url`.
One tool call instead of two. 1,000 queries/month ≈ 33/day, more than enough.


---

## 3. Interaction with Existing Architecture

### hal/judge.py

**New `_ACTION_TIERS` entries:**
```python
"web_search": 0,    # Query goes to external API — read-only, but logged
"fetch_url": 1,     # Arbitrary URL fetch — needs SSRF protection
```

**New URL validation:**
- `_validate_url()` blocks RFC1918, loopback, link-local, non-HTTPS, `.local`/`.internal`
- Called from `_dispatch` before `fetch_url` executes
- Regex-scan search queries for RFC1918 addresses and reject if found

### hal/agent.py

- Two new TOOLS entries (`web_search`, `fetch_url`) with explicit privacy instructions
  in descriptions
- Two new `_dispatch` cases calling `hal.web.*`
- Conditional inclusion: only add tools if `config.tavily_api_key` is set
- KB seeding is unaffected — web results are ephemeral tool output, not persistent knowledge

### hal/intent.py

- Add 5-10 agentic examples implying web search (e.g., "what's the latest version of
  prometheus", "search for vllm cuda compatibility")

### harvest/collect.py — Future extension

- `collect_release_feeds()` — fetch RSS for key software, ingest release notes
- `collect_web_bookmarks()` — re-fetch curated URL list, re-ingest
- Both share `fetch_url` infrastructure but run in batch with own `doc_tier`
- **Not part of initial implementation**

### hal/knowledge.py — Future doc_tier

| Tier | Name | Source | Freshness |
|------|------|--------|-----------|
| `ground-truth` | Ground Truth | `knowledge/*.md` | User-maintained |
| `reference` | Reference | Local static docs | Nightly harvest |
| `live-state` | Live State | Lab commands | Nightly harvest |
| `memory` | Memory | `/remember` | User-created |
| **`web-cache`** | **Web Cache** | **Fetched URLs** | **TTL-based expiry** |

Not needed for initial implementation — add when/if query-result caching is wanted.

### hal/config.py

```python
tavily_api_key: str   # TAVILY_API_KEY — empty string disables web_search
```

Pattern: same as `TELEGRAM_BOT_TOKEN` — empty means disabled, tool not included in TOOLS.


---

## 4. MCP (Model Context Protocol)

### What it is

Open protocol (Anthropic, adopted broadly 2025-2026) that standardizes how AI apps
discover, authenticate with, and call tools. Tools are served by MCP servers — standalone
processes exposing tools over JSON-RPC (stdio or HTTP+SSE transport).

### Relevant community MCP servers (2026)

| MCP Server | What it does | HAL overlap |
|-----------|-------------|-------------|
| `mcp-server-fetch` | Fetch URLs, extract text | `fetch_url` |
| `mcp-server-brave-search` | Brave Search wrapper | `web_search` |
| `mcp-server-github` | Full GitHub API | Future GitHub tools |
| `mcp-server-filesystem` | Read/write/search files | `read_file`/`write_file` |
| `mcp-server-prometheus` | PromQL queries | `get_metrics` |
| `mcp-server-docker` | Container management | `run_command` docker subset |

### Should HAL adopt MCP?

**Not now. Probably eventually.**

**Against (now):**
1. Judge is non-negotiable — MCP servers execute tools inside their process; inserting
   Judge requires wrapping every server in a proxy, defeating the simplicity benefit
2. Tool list is small (~15 tools) — MCP's benefit is "pluggable hundreds of tools"
3. Debugging is harder — JSON-RPC over stdio vs. reading `_dispatch()` directly
4. Extra processes — overhead on a constrained homelab

**For (eventually):**
1. Community tools without writing code (e.g., `mcp-server-github`)
2. Protocol standardization for interop
3. Separation of concerns — external tools stay external

**Recommended path:** Keep hand-wiring. When tool count exceeds ~20, or when a community
MCP server saves >100 lines, add MCP as optional transport alongside `_dispatch()`.
Judge wraps the MCP call — `approve()` runs before `tools/call` is forwarded.


---

## 5. What NOT to Do

### Mistake 1: Letting the LLM prefer web over KB
Give both `search_kb` and `web_search` → LLM defaults to web for everything.
**Fix:** Tool description says "try search_kb first." Monitor via audit log.

### Mistake 2: Caching web results without TTL
Stale cached content pollutes future searches.
**Fix:** Don't cache in v1. If added later, use `web-cache` tier with explicit TTL.

### Mistake 3: Not blocking SSRF in `fetch_url`
The single most dangerous mistake. LLM requests internal URLs → reads internal services.
**Fix:** URL validation before HTTP request — block private ranges, resolve DNS first,
re-validate each redirect hop.

### Mistake 4: Trusting content from fetched web pages
Fetched pages can contain prompt injection (invisible text with malicious instructions).
**Fix:** Judge gates all tool calls regardless; delimit web content clearly; cap size.

### Mistake 5: Adding too many web tools at once
20 tools + MAX_ITERATIONS=8 = wasted iterations trying different web tools.
**Fix:** One capability at a time. Ship, eval, then add the next.

### Mistake 6: Not updating the eval suite
24 existing eval queries don't test web access.
**Fix:** Add 5-10 web-specific eval queries + negative tests (KB should suffice).

### Mistake 7: Forgetting Telegram auto-approves only tier 0
`ServerJudge` denies above tier 0. If `fetch_url` is tier 1, it silently fails via
Telegram. Decide explicitly: make it tier 0 (if SSRF protection is solid) or add
Telegram approval flow.


---

## 6. Implementation Plan

### Step 1 — `web_search` (Tavily)

**Adds:** `web_search(query) -> list[dict]` via Tavily SDK

**Files:** `hal/web.py` (new), `hal/config.py`, `hal/agent.py`, `hal/judge.py`,
`hal/intent.py`, `.env.example`, `requirements.txt`, `tests/test_web.py` (new)

**Verify:** `pytest tests/test_web.py -v`; on server ask "latest version of Prometheus";
audit log shows `web_search` tier 0

**Depends on:** Nothing


### Step 2 — `fetch_url` with SSRF protection

**Adds:** `fetch_url(url) -> str` with URL validation blocking private networks

**Files:** `hal/web.py`, `hal/agent.py`, `hal/judge.py`, `tests/test_web.py`

**Verify:** pytest passes including SSRF negative tests; fetch public URL works;
`http://localhost:8000` is blocked

**Depends on:** Step 1 (shared module)


### Step 3 — Eval suite expansion

**Adds:** 8-10 web-specific eval queries + `web_tool_accuracy` evaluator

**Files:** `eval/queries.jsonl`, `eval/evaluate.py`

**Verify:** `python -m eval.run_eval && python -m eval.evaluate --skip-llm-eval`

**Depends on:** Steps 1 + 2


### Step 4 — ServerJudge tier decision for Telegram

**Adds:** Explicit policy on web tool availability via Telegram

**Files:** `hal/server.py`, possibly `hal/judge.py`, `tests/test_telegram.py`

**Verify:** Web query via Telegram either works or gives clear message

**Depends on:** Steps 1 + 2


### Step 5 — Query sanitization + audit monitoring

**Adds:** `_sanitize_search_query()` + `/web_stats` slash command

**Files:** `hal/web.py`, `hal/main.py`, `tests/test_web.py`

**Verify:** Query containing `192.168.5.10` is rejected; `/web_stats` shows counts

**Depends on:** Step 1


### Step 6 — (Future) Harvest web feeds

**Adds:** `collect_release_feeds()` for RSS ingestion with `web-cache` doc_tier

**Files:** `harvest/collect.py`, `harvest/ingest.py`, `hal/knowledge.py`, `hal/config.py`

**Depends on:** Steps 1 + 2


### Step 7 — (Future) GitHub API integration

**Adds:** Read-only GitHub tools: issues, releases, code search

**Files:** `hal/github.py` (new), `hal/agent.py`, `hal/judge.py`, `hal/config.py`

**Depends on:** Steps 1-5 proven stable
