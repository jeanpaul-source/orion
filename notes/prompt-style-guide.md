# Prompt Style Guide — "Guardrails Not Rails"

> Established: Chat 11 · Applies to all future chat prompts

---

## Why this exists

Chats 2–10 used prescriptive prompts: every line of code spelled out, every
design decision pre-made. That works for mechanical tasks (ruff cleanup, test
coverage) but fails for tasks with genuine design questions — it forces
decisions before the executing agent has seen the codebase, and prevents it
from adapting to what it discovers during implementation.

This guide defines the new standard: **lock what must be locked, leave open
what should be discovered**.

---

## Four sections, in order

Every chat prompt follows this structure:

### 1. Mission (what, not how)

One paragraph that describes the **capability being added** in plain terms.
What does the user get that they don't have today? Frame it as a before/after.

Do not describe implementation here. "HAL can execute Python code in an
isolated environment" — not "create `hal/sandbox.py` with a `run_code()`
function."

### 2. Non-negotiables (locked)

Things the executing agent **cannot** deviate from. These are load-bearing
constraints, not suggestions. If something here needs to change, the agent
must stop and ask.

Examples of non-negotiables:
- CLAUDE.md format (one change at a time, explain before acting)
- All actions through the Judge
- `make check` passes after each commit
- Specific files that must be updated (docs, config)
- Security boundaries (no Docker socket mounts, no bypass of audit)
- Testing requirements (offline, mocked, specific fixtures)

Keep this list tight. If it's longer than ~15 items, some of them are
preferences, not constraints. Move those to open questions.

### 3. Open design decisions (flagged with trade-offs)

Things the executing agent **must decide** and **must justify** (via the
CLAUDE.md format) before implementing. For each question:

- State the question clearly
- List 2–3 realistic options
- Describe the trade-off for each (not just pros — include the cost)
- Say which option the prompt author would lean toward, if any — but
  explicitly say "your call"

The agent picks one, states why in the CLAUDE.md format block, and proceeds.
If the operator disagrees, they say so at the proposal step.

Examples of open design decisions:
- Isolation strategy (Docker-in-Docker vs subprocess vs SSH)
- Resource limits and defaults
- When the LLM should use tool A vs tool B
- Naming, module structure, handler placement

### 4. Completion checklist

A concrete list of verifiable conditions that mean "this work is done."
Not implementation steps — outcomes.

Examples:
- "HAL can execute `print('hello')` via the sandbox tool and return `hello`"
- "Tests cover: success, timeout, denial, OOM"
- "`make check` passes on the final commit"
- "ARCHITECTURE.md documents the new component"

---

## Rules for prompt authors

1. **Don't design it if you don't have to.** If the implementation is
   obvious, it doesn't need a section. If it requires thought, flag it
   as an open question.

2. **Lock security, unlock architecture.** Security constraints are
   non-negotiable. Module structure is a design decision.

3. **Current state goes in the prompt.** Every prompt should include
   accurate file names, line counts, test counts, and branch state.
   Stale data leads to wrong decisions.

4. **Reference existing docs, don't repeat them.** "Follow CLAUDE.md"
   is better than copying CLAUDE.md into the prompt.

5. **Name the files that must be touched.** Even in an open-ended prompt,
   say which files will definitely need changes (config, docs, tests).
   This prevents the agent from touching unexpected files.

6. **One prompt = one feature.** Don't combine unrelated work. Each
   prompt should be completable in one branch with a single PR.

---

## Anti-patterns (things the old style got wrong)

| Anti-pattern | Problem | Fix |
|---|---|---|
| Spelling out every line of code | Agent copies instead of thinks; can't adapt | Describe the capability, not the code |
| Pre-deciding all design questions | Prompt author guessed wrong; agent can't correct | Flag as open question with trade-offs |
| No current-state section | Agent works from stale assumptions | Include file sizes, test counts, branch |
| Mixing mechanical + design work | One prompt tries to do too much | Split into separate prompts |
| Repeating CLAUDE.md rules verbatim | Wastes context, drifts from source | "Follow CLAUDE.md" + one-line summary |

---

## When to still use prescriptive style

Some tasks genuinely benefit from step-by-step instructions:

- **Pure mechanical work** — ruff fixes, dependency bumps, CI config
- **Known-good patterns being replicated** — "add the same test pattern
  we used for module X to module Y"
- **Operational runbooks** — deploy steps, rollback procedures

If the task has zero design ambiguity, prescriptive is fine. The risk is
applying prescriptive style to tasks that have real decisions to make.
