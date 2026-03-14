# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## Before Every Code Change

**Principles — these apply regardless of which AI tool or IDE is in use.**

1. **Identify root cause, not symptom.** Before changing anything, state what is
   actually wrong and why. If the explanation sounds thin, it probably is.

2. **One logical change per commit.** Each commit should do one thing. This makes
   diffs easy to review and safe to revert. "Logical" means one finding, one fix,
   one feature — not one line.

3. **State confidence honestly.** Say whether you *know* this is correct or are
   *guessing*. Confident-sounding guesses are the most dangerous failure mode.

4. **Make changes easy to review.** In VS Code the user reviews actual file diffs.
   Keep changes small, focused, and well-commented so the diff tells the story.

5. **Verify after each change.** Run `make check` (or the relevant subset) after
   every commit. Don't stack unverified changes.

If the user says **"split"**, break the current work into smaller commits.
If the user says **"why"**, explain the root cause before continuing.

---

## ⛔ CLAUDE.md Maintenance Rule

**This file is a reference document, not a changelog or session journal.**

- **Update in place.** When facts change (new service, new file, new tool), edit the
  relevant existing section. Never append a new "Done" or "Session N" block.
- **Do not add session logs.** Git history is the changelog. This file describes
  *current state*, not *how we got here*.
- **If a section is growing beyond its original scope**, that is drift. Condense it.
- **Implementation details** (test counts, intermediate thresholds, migration steps, item
  numbers) belong in commit messages, not here.

If I catch myself adding a changelog section, I must stop and instead update the
existing "Current State" section in place.

---

## How the AI Assistant Works With the Developer

**Why this section exists:** AI assistants drift on long projects. Each individual fix
looks plausible in isolation, but over many sessions the thread of what we're building
gets lost. The mitigation is transparency — the AI must explain its reasoning so the
developer can catch when the reasoning is wrong or shallow.

**Rules — no exceptions:**

1. **Explain before acting.** Before writing or changing code, state:
   - What the problem actually is (root cause, not symptom)
   - What you propose to do and why it's correct long-term
   - Whether you *know* this is right or are *guessing*
   In VS Code, this explanation goes in your chat message. The developer then
   reviews the actual file diffs you produce.

2. **One change at a time.** Make one logical change, verify it works, then move
   to the next. Multiple simultaneous changes make it impossible to know what
   worked or broke.

3. **No bandaids.** If you find yourself adding rules, caps, flags, or prompt
   instructions to work around a misbehaving component — stop and ask: is the
   component itself wrong? Patching symptoms is how drift accumulates silently.

4. **Say "I'm guessing" out loud.** If you don't fully understand why something
   is broken, say so explicitly before proposing a fix.

---

## Documentation

See [README.md](README.md) for the full documentation index. Key references:
ARCHITECTURE.md (design), OPERATIONS.md (deploy/ops), CONTRIBUTING.md (dev workflow).

---

## Memory Protocol

At session start, read `memory/SUMMARY.md` for current project state.

At session end, if any of these happened, propose an update to `memory/SUMMARY.md`:

- Code was merged or committed
- An architectural decision was made
- An issue was discovered or resolved
- Project state changed meaningfully

Updates follow the standard edit workflow — propose the change, human reviews
via git diff. If `Last updated` is more than 7 days old, flag this to the user.
