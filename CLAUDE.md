# Orion

All project conventions are in [`.github/copilot-instructions.md`](.github/copilot-instructions.md).
This file exists for Claude Code compatibility. Do not duplicate rules here.

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
