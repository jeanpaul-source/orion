# Orion

A personal homelab AI assistant built intentionally. It knows the infrastructure, answers
questions about it, takes actions within it, monitors health, learns over time, and guards
the home network.

---

## ⛔ REQUIRED FORMAT — Before Every Code Change

**This applies to every single change, no exceptions. Violations are drift.**

For each proposed change I must output exactly this block and then **STOP and wait**:

```markdown
### Item N — <short title>

**Root cause (not symptom):** <what is actually wrong and why>

**What I propose:** <exact files and lines I will touch, and what I will do>

**Why this is correct long-term:** <not just "it fixes the symptom">

**Confidence:** I KNOW this is right / I am GUESSING because <reason>
```

I do **not** write or change any code until the operator replies with approval.
If I have a genuine question before proceeding — approach choice, ambiguity, preference
— I use `AskUserQuestion` **before** or **alongside** the proposal block. Asking a
question is a valid form of waiting; it does not violate the stop-and-wait rule.
After the operator approves, I make **exactly one change**, verify it, commit it,
then present the **next** item in the same format and stop again.

**"One change" is not open to interpretation:** one finding number = one commit. Each
item gets its own proposal block, its own approval, its own `pytest` run, its own commit.

The only exception: a change that is **mechanical and zero-risk** (e.g. a 2-line
whitespace or import fix) may be grouped with the preceding item **only if I explicitly
state** "I am grouping this with the above as a single commit because it is trivially
mechanical" **and the operator confirms it**. Grouping without that explicit exchange is
a violation.

If I skip this format, the operator should say **"format"** and I will stop, restate
the plan correctly, and wait.

If I batch items without permission, the operator should say **"split"** and I will
re-propose them separately.

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

## How I (Claude) Work With the Operator

**The reason this section exists:** I drift on long projects. Each individual fix can seem
logical in isolation, but over many sessions and context resets I lose the thread of what
we're actually building and start optimising for "make the immediate problem go away" instead
of "build something genuinely reliable." The operator cannot see this drift from the outside —
each thing I do looks plausible, the code runs, the symptom disappears. The only way to
surface drift is to force me to explain my reasoning in full before every action, because when
I'm drifting the explanation will sound wrong or thin. That is the catch mechanism.

**Rules — no exceptions:**

1. **Explain before acting.** Before writing or changing any code I must state:
   - What I think the problem actually is (root cause, not symptom)
   - What I propose to do and why this approach is correct long-term
   - Whether I *know* this is right or whether I am *guessing*
   Then wait for the operator to agree before proceeding.

2. **One change at a time.** Make one change, verify it works, then move to the next.
   Multiple simultaneous changes make it impossible to know what worked or broke.

3. **No bandaids.** If I find myself adding rules, caps, flags, or prompt instructions to
   work around a misbehaving component, I must stop and ask: is the component itself wrong?
   Patching symptoms is how drift accumulates silently.

4. **Say "I'm guessing" out loud.** If I don't fully understand why something is broken,
   I say so explicitly before proposing a fix. Confident-sounding guesses are the most
   dangerous thing I do.

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
