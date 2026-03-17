---
description: "Verify an audit finding against current code — check if it's fixed, still present, or outdated"
agent: agent
argument-hint: "Finding ID (e.g., F-85) or description"
---

# Verify Finding

Verify whether an audit finding is still present in the codebase.

1. **Find the finding** in [docs/planning-pack/audit-findings.md](docs/planning-pack/audit-findings.md).
   Extract the claimed issue, affected file(s), and line numbers.

2. **Read the actual code** at those locations. Do not trust the finding's
   quoted code — it may be outdated.

3. **Classify the finding** as one of:
   - **Still present** — the code matches the finding's description
   - **Fixed** — the code has been changed and no longer has the issue
   - **Outdated** — the file or function no longer exists
   - **Partially fixed** — some aspects addressed, others remain

4. **Report** with evidence: show the relevant current code and explain
   your classification. State your confidence level.
